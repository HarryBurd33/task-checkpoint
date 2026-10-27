"""Pure routing decisions; execution and ownership belong to the dispatcher."""
import datetime as dt
import checkpoint as cp
import telemetry


def require(condition, message):
    if not condition:
        raise cp.Fault('Routing: ' + message)


def strings(value):
    return isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)


def validate_output_schema(value, depth=0):
    require(isinstance(value, dict) and depth <= 8, 'bounded output schema required')
    require(set(value) <= {'type','properties','required','items','additionalProperties','enum'}, 'unsupported output schema field')
    require(value.get('type') in ('object','array','string','number','integer','boolean','null'), 'output schema type required')
    require(len(cp.encoded(value)) <= 16384, 'output schema exceeds bound')
    if 'properties' in value:
        require(isinstance(value['properties'], dict), 'schema properties must be an object')
        for child in value['properties'].values(): validate_output_schema(child, depth+1)
    if 'items' in value: validate_output_schema(value['items'], depth+1)
    if 'required' in value: require(strings(value['required']), 'schema required fields must be strings')
    if 'additionalProperties' in value: require(isinstance(value['additionalProperties'], bool), 'schema additionalProperties must be boolean')
    if 'enum' in value: require(isinstance(value['enum'], list) and bool(value['enum']) and all(not isinstance(x,(dict,list)) for x in value['enum']), 'schema enum must contain scalars')
    return value


def validate_task(task):
    cp.validate(task, cp.read(cp.ASSETS / 'task.schema.json'))
    if 'routing' not in task:
        return task
    r = task['routing']
    fields = {'id', 'task_class', 'complexity', 'risk', 'required_tools', 'privacy',
              'allowed_providers', 'budget', 'dependencies', 'estimated_work_seconds',
              'acceptance', 'escalation_reason', 'bounds', 'work_packages', 'output_schema'}
    require(isinstance(r, dict) and set(r) <= fields and fields - {'escalation_reason', 'bounds', 'work_packages', 'output_schema'} <= set(r), 'invalid routing fields')
    if 'output_schema' in r:
        validate_output_schema(r['output_schema'])
    if 'work_packages' in r:
        from planner import validate
        validate(r['work_packages'])
    if 'bounds' in r:
        bounds = r['bounds']
        require(isinstance(bounds, dict) and set(bounds) == {'permitted_files', 'permitted_actions', 'checkpoint_boundary', 'assignment'}, 'invalid bounds')
        require(strings(bounds['permitted_files']) and strings(bounds['permitted_actions']), 'invalid permitted bounds')
        for path in bounds['permitted_files']:
            cp.relative(path)
    for key in ('id', 'task_class'):
        require(isinstance(r[key], str) and bool(r[key].strip()), key + ' required')
    require(r['complexity'] in ('routine', 'complex'), 'invalid complexity')
    require(r['risk'] in ('low', 'high'), 'invalid risk')
    require(r['privacy'] in ('public', 'private', 'local_only'), 'invalid privacy')
    require(strings(r['required_tools']) and strings(r['allowed_providers']), 'invalid tool/provider lists')
    require(r.get('escalation_reason') is None or isinstance(r['escalation_reason'], str) and r['escalation_reason'].strip(), 'invalid escalation reason')
    budget = r['budget']
    require(isinstance(budget, dict) and set(budget) == {'max_attempts', 'max_wall_seconds', 'max_api_usd'}, 'invalid budget')
    require(isinstance(budget['max_attempts'], int) and not isinstance(budget['max_attempts'], bool) and budget['max_attempts'] > 0, 'invalid attempts budget')
    require(telemetry.number(budget['max_wall_seconds']) and budget['max_wall_seconds'] > 0, 'invalid wall budget')
    require(budget['max_api_usd'] is None or telemetry.number(budget['max_api_usd']) and budget['max_api_usd'] >= 0, 'invalid API budget')
    require(telemetry.number(r['estimated_work_seconds']) and r['estimated_work_seconds'] > 0, 'invalid work estimate')
    require(isinstance(r['dependencies'], list), 'invalid dependencies')
    for dep in r['dependencies']:
        require(isinstance(dep, dict) and isinstance(dep.get('id'), str) and bool(dep['id']) and dep.get('status') in ('completed', 'pending', 'running', 'failed', 'unknown', 'cancelled'), 'invalid dependency')
    require(isinstance(r['acceptance'], list) and bool(r['acceptance']), 'acceptance required')
    ids = []
    for check in r['acceptance']:
        require(isinstance(check, dict) and set(check) == {'id', 'argv'} and isinstance(check['id'], str) and bool(check['id']) and strings(check['argv']) and bool(check['argv']), 'invalid acceptance command')
        ids.append(check['id'])
    require(len(ids) == len(set(ids)), 'duplicate acceptance IDs')
    return task


def _decide(task, config, signals, history, current_worker=None, override=None, trigger='boundary', now=None, assessment=None, worker_assessor=None):
    validate_task(task)
    current = telemetry.timestamp(now) if now is not None else dt.datetime.now(dt.timezone.utc)
    summary = assessment if assessment is not None else telemetry.assess(signals, current, config.get('telemetry_max_age_seconds', 120))
    def result(action, reason, worker=None):
        return {'action': action, 'worker_id': worker.get('id') if worker else None,
                'reasons': [reason], 'effort': worker.get('effort', 'medium') if worker else None,
                'telemetry': summary}
    if config.get('pause'):
        return result('pause', 'routing paused by configuration')
    r = task.get('routing')
    if not r:
        return result('manual', 'task has no routing contract')
    if any(d['status'] != 'completed' for d in r['dependencies']):
        return result('pause', 'dependencies incomplete')
    if not isinstance(history, list) or any(not isinstance(h, dict) for h in history):
        return result('manual', 'invalid attempt history')
    if any(h.get('status') not in ('accepted', 'rejected') for h in history):
        return result('pause', 'attempt outcome uncertain')
    budget = r['budget']
    if len(history) >= budget['max_attempts']:
        return result('pause', 'attempt budget exhausted')
    wall = [h.get('wall_seconds') for h in history]
    if any(not telemetry.number(v) or v < 0 for v in wall):
        return result('pause', 'observed wall usage unknown')
    if sum(wall) + r['estimated_work_seconds'] > budget['max_wall_seconds']:
        return result('pause', 'wall budget exhausted')
    failures = [h for h in history if h['status'] == 'rejected']
    if len(failures) > config.get('max_retries', 1):
        return result('pause', 'retry budget exhausted')
    if summary['statuses']['context'] == 'low':
        return result('pause', 'context headroom low; checkpoint and renew context')
    if summary.get('override_blocked') or summary['statuses']['codex_plan'] == 'low':
        return result('pause', 'account reserve reached; stop ordinary work across shared allowance')
    workers = config.get('workers', [])
    if not isinstance(workers, list):
        return result('manual', 'invalid workers configuration')
    current_id = current_worker.get('id') if isinstance(current_worker, dict) else current_worker
    override_id = override.get('worker_id') if isinstance(override, dict) else override
    failed_ids = {h.get('worker_id') for h in failures}
    failed_ranks = [w.get('rank', 0) for w in workers if w.get('id') in failed_ids]
    eligible = []
    rejected = []
    for w in workers:
        reasons = []
        wid = w.get('id')
        if not wid or not w.get('model') or not w.get('provider') or w.get('enabled') is not True or w.get('available') is not True:
            reasons.append('worker disabled or unavailable')
        availability = w.get('availability', {})
        try:
            age = (current - telemetry.timestamp(availability.get('observed_at'))).total_seconds()
            if not availability.get('source') or not 0 <= age <= config.get('availability_max_age_seconds', 86400):
                reasons.append('availability evidence stale or missing')
        except (ValueError, TypeError):
            reasons.append('availability evidence missing')
        if w.get('provider') not in r['allowed_providers'] or w.get('provider') not in config.get('allowed_providers', []):
            reasons.append('provider forbidden')
        if not set(r['required_tools']) <= set(w.get('tools', [])):
            reasons.append('required tools unavailable')
        if r['privacy'] not in w.get('privacy', []) or r['privacy'] == 'local_only' and w.get('billing') != 'local':
            reasons.append('privacy permission missing')
        if r['complexity'] == 'complex' and w.get('max_complexity') != 'complex':
            reasons.append('complexity unsupported')
        q = w.get('qualification', {})
        try:
            qage = (current - telemetry.timestamp(q.get('observed_at'))).total_seconds()
        except (ValueError, TypeError):
            qage = -1
        if (q.get('model') != w.get('model') or q.get('effort') != w.get('effort') or q.get('passed') is not True or r['task_class'] not in q.get('task_classes', []) or not q.get('source')
                or not isinstance(q.get('samples'), int) or isinstance(q.get('samples'), bool) or q['samples'] < 1
                or not telemetry.number(q.get('acceptance_rate')) or not 0 < q['acceptance_rate'] <= 1
                or not telemetry.number(q.get('mean_total_seconds')) or q['mean_total_seconds'] <= 0
                or qage < 0 or qage > config.get('qualification_max_age_seconds', 2592000)):
            reasons.append('qualification evidence missing or stale')
        # task_classes names the reviewed qualification scope; tools/privacy here
        # are optional narrower evidence coverage, separate from permissions above.
        if 'required_tools' in q and not set(r['required_tools']) <= set(q['required_tools']):
            reasons.append('qualification does not cover required tools')
        if 'privacy' in q and r['privacy'] not in q['privacy']:
            reasons.append('qualification does not cover privacy scope')
        if w.get('interface') == 'local_text':
            if q.get('model_digest') != w.get('model_digest'):
                reasons.append('local model digest differs from qualification')
            if q.get('output_schema_sha256') != cp.sha(cp.encoded(r.get('output_schema'))):
                reasons.append('local output schema differs from qualification')
        billing = w.get('billing')
        worker_summary = summary
        if billing == 'plan' and w.get('account_fingerprint'):
            worker_signals = signals.get('accounts', {}).get(w['account_fingerprint'], {'records': []})
            worker_summary = worker_assessor(worker_signals) if worker_assessor else telemetry.assess(worker_signals, current, config.get('telemetry_max_age_seconds', 120))
        kind = {'plan': 'codex_plan', 'api': 'api_balance', 'local': 'local_resource'}.get(billing)
        if kind is None:
            reasons.append('unsupported billing')
        elif worker_summary['statuses'][kind] == 'low':
            reasons.append(kind + ' headroom low')
        elif worker_summary['statuses'][kind] == 'unknown' and (w.get('account_fingerprint') or config.get('unknown_telemetry', 'manual') != 'explicit_budget'):
            reasons.append(kind + ' headroom unknown')
        if billing == 'api':
            costs = [h.get('api_cost_usd') for h in history]
            cap = budget['max_api_usd']
            if config.get('allow_paid') is not True or cap is None or cap <= 0:
                reasons.append('paid API not authorized')
            elif any(not telemetry.number(v) or v < 0 for v in costs):
                reasons.append('observed API cost unknown')
            elif sum(costs) >= cap:
                reasons.append('API budget exhausted')
        if w.get('effort', 'medium') not in ('low', 'medium') and not (failures or r.get('escalation_reason')):
            reasons.append('higher effort needs escalation reason')
        rank = w.get('rank')
        if not telemetry.number(rank) or rank < 0:
            reasons.append('invalid worker rank')
        elif failed_ranks and rank <= max(failed_ranks):
            reasons.append('failure requires higher qualified worker')
        if wid in failed_ids:
            reasons.append('failed worker cannot be retried automatically')
        if override_id and wid != override_id:
            reasons.append('different override worker')
        if reasons:
            rejected.append(str(wid) + ': ' + ', '.join(reasons))
        else:
            eligible.append(w)
    if not eligible:
        out = result('manual', 'no permitted qualified worker')
        out['reasons'].extend(rejected)
        return out
    eligible.sort(key=lambda w: (w.get('estimated_relative_cost', float('inf')), useful_seconds(w), w['rank'], w['id']))
    selected = eligible[0]
    existing = next((w for w in eligible if w['id'] == current_id), None)
    prefer_local = config.get('prefer_local_for_qualified') is True and selected.get('billing') == 'local' and existing and existing.get('billing') != 'local'
    if existing and selected['id'] != current_id and not override_id and not failures and not prefer_local:
        if r['estimated_work_seconds'] < config.get('minimum_task_seconds', 30):
            selected = existing
        else:
            try:
                last = telemetry.timestamp(history[-1]['finished_at']) if history else None
                cooling = last is not None and (current - last).total_seconds() < config.get('cooldown_seconds', 300)
            except (ValueError, TypeError, KeyError):
                cooling = True
            benefit = useful_seconds(existing) - useful_seconds(selected)
            if cooling or benefit <= config.get('switch_cost_seconds', 20):
                selected = existing
    if selected.get('interface') not in ('command', 'codex_exec', 'local_text', 'fixture'):
        return result('manual', 'worker requires manual interface', selected)
    return result('launch', 'qualified worker within permissions and budget', selected)


def useful_seconds(worker):
    """Observed total effort per useful acceptance, including failed attempts."""
    q = worker['qualification']
    return q['mean_total_seconds'] / q['acceptance_rate']


def validate_config(config):
    require(isinstance(config, dict), 'config must be an object')
    require(isinstance(config.get('workers'), list), 'workers must be a list')
    require(strings(config.get('allowed_providers')), 'config providers must be a list')
    for field in ('allow_paid', 'pause', 'prefer_local_for_qualified'):
        if field in config:
            require(isinstance(config[field], bool), field + ' must be boolean')
    for field in ('minimum_task_seconds', 'cooldown_seconds', 'switch_cost_seconds',
                  'telemetry_max_age_seconds', 'availability_max_age_seconds',
                  'qualification_max_age_seconds'):
        if field in config:
            require(telemetry.number(config[field]) and config[field] >= 0, field + ' must be nonnegative')
    if 'max_retries' in config:
        require(isinstance(config['max_retries'], int) and not isinstance(config['max_retries'], bool)
                and config['max_retries'] >= 0, 'max_retries must be nonnegative integer')
    require(config.get('unknown_telemetry', 'manual') in ('manual', 'explicit_budget'), 'invalid unknown telemetry policy')
    ids = []
    for worker in config['workers']:
        require(isinstance(worker, dict), 'worker must be an object')
        require(isinstance(worker.get('id'), str) and bool(worker['id']), 'worker ID required')
        ids.append(worker['id'])
        for field in ('model', 'provider'):
            require(isinstance(worker.get(field), str) and bool(worker[field].strip()), 'worker ' + field + ' required')
        for field in ('available', 'enabled'):
            require(isinstance(worker.get(field), bool), 'worker ' + field + ' must be boolean')
        for field, allowed in (('billing', ('plan', 'api', 'local')),
                               ('max_complexity', ('routine', 'complex')),
                               ('effort', ('low', 'medium', 'high', 'xhigh', 'max', 'ultra')),
                               ('interface', ('command', 'codex_exec', 'local_text', 'manual', 'fixture'))):
            require(worker.get(field) in allowed, 'invalid worker ' + field)
        for field in ('tools', 'privacy'):
            require(strings(worker.get(field)), 'worker ' + field + ' must be a list')
        if worker.get('codex_home') or worker.get('account_fingerprint'):
            from pathlib import Path
            ident = worker.get('account_fingerprint')
            require(isinstance(worker.get('codex_home'), str) and Path(worker['codex_home']).is_absolute(), 'explicit profile home required')
            require(isinstance(ident, str) and len(ident) == 64 and all(c in '0123456789abcdef' for c in ident), 'pinned account identity required')
            require(worker.get('billing') == 'plan' and worker.get('provider') == 'openai', 'profile only applies to ChatGPT plan workers')
        if worker.get('interface') == 'local_text':
            from local_text_worker import endpoint
            require(worker.get('provider') == 'ollama' and worker.get('billing') == 'local' and not worker.get('tools'), 'local text is tool-free and unpaid')
            endpoint(worker.get('endpoint', ''))
            require(isinstance(worker.get('model_digest'), str) and len(worker['model_digest']) == 64, 'local model digest required')
        for field in ('availability', 'qualification'):
            require(isinstance(worker.get(field, {}), dict), 'worker ' + field + ' must be an object')
        for evidence in (worker.get('availability', {}), worker.get('qualification', {})):
            if 'source' in evidence and evidence['source'] is not None:
                require(isinstance(evidence['source'], str), 'evidence source must be a string')
            if evidence.get('observed_at'):
                try:
                    telemetry.timestamp(evidence['observed_at'])
                except (TypeError, ValueError, OverflowError):
                    raise cp.Fault('Routing: invalid evidence timestamp')
        if 'estimated_relative_cost' in worker:
            require(telemetry.number(worker['estimated_relative_cost']) and worker['estimated_relative_cost'] >= 0, 'invalid estimated relative cost')
        q = worker.get('qualification', {})
        if 'passed' in q:
            require(isinstance(q['passed'], bool), 'qualification passed must be boolean')
        if 'samples' in q:
            require(isinstance(q['samples'], int) and not isinstance(q['samples'], bool) and q['samples'] >= 0, 'qualification samples must be nonnegative integer')
        for field in ('acceptance_rate', 'mean_total_seconds'):
            if field in q:
                require(telemetry.number(q[field]) and q[field] >= 0, 'invalid qualification ' + field)
        if 'acceptance_rate' in q:
            require(q['acceptance_rate'] <= 1, 'acceptance rate exceeds one')
        for field in ('task_classes', 'required_tools', 'privacy'):
            if field in q:
                require(strings(q[field]), 'qualification ' + field + ' must be a list')
        require(telemetry.number(worker.get('rank')) and worker['rank'] >= 0, 'invalid worker rank')
    require(len(ids) == len(set(ids)), 'duplicate worker IDs')
    return config


def decide(task, config, signals, history, current_worker=None, override=None,
           trigger='boundary', now=None, assessment=None, worker_assessor=None):
    """Fail closed on malformed configuration rather than leaking Python errors."""
    try:
        validate_config(config)
        return _decide(task, config, signals, history, current_worker, override, trigger, now, assessment, worker_assessor)
    except cp.Fault:
        raise
    except (TypeError, ValueError, AttributeError, KeyError, IndexError, OverflowError) as exc:
        raise cp.Fault('Routing: malformed input (' + type(exc).__name__ + ')') from exc
