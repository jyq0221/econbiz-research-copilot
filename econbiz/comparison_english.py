"""English presentation labels; preserve user supplied identities and numeric text."""


def english_display(display, c):
    groups = {}
    for i, m in enumerate(c['models']):
        y = next(v for v in c['variables'] if v['members'].get(m['run']['id']) == m['actual_spec']['y'])
        groups.setdefault(y['id'], (y, []))[1].append((i, m))
    model_tables = iter(t for t in display['tables'] if t['kind'] == 'models')
    labels = ['Observations', 'Entities', 'Observed years', 'Regressors', 'Controls', 'Fixed effects',
              'Standard errors', 'Cluster field', 'Clusters', 'Engine', 'Model role', 'Numerical check']
    for y, group in groups.values():
        for start in range(0, len(group), 6):
            subset = group[start:start+6]; table = next(model_tables)
            table['title'] = 'Dependent variable: '+y['label']+' ('+(y['unit'] or 'unit not provided')+')'
            table['header'][0] = 'Variable'
            for row in table['rows'][:-12]:
                row[1:] = ['Not included' if v == '未纳入' else v for v in row[1:]]
            stats = table['rows'][-12:]
            for row, label in zip(stats, labels): row[0] = label
            for j, (_, m) in enumerate(subset, 1):
                stats[2][j] = ', '.join(m['sample']['periods'])
                stats[3][j] = ', '.join(m['actual_spec']['x'])
                stats[4][j] = ', '.join(m['controls']) or 'None'
                stats[5][j] = ', '.join(m['actual_spec']['fixed_effects'])
                stats[7][j] = m['actual_spec']['standard_errors'].get('field') or 'Not applicable'
                stats[8][j] = str(m['diagnostics'].get('cluster_count') or 'Not applicable')
                stats[10][j] = {'baseline':'Baseline','robustness':'Robustness','other':'Other'}[m['role']]
                stats[11][j] = 'Independently checked'
            table['notes'] = ['Standard errors in parentheses. Coefficients describe conditional associations. Exact p-values, confidence intervals and full parameters remain in the comparison record.']
            if c['stars']:
                table['notes'].append('; '.join(f'{label} p < {t}' for t,label in c['stars'])+'; based on unrounded p-values.')
            if c['display_terms'] is not None:
                table['notes'].append('Displayed variables: '+', '.join(c['display_terms'])+'. Other parameters remain in the complete record.')
    for table in display['tables']:
        if table['kind'] == 'definitions':
            table.update(title='Variable definitions', header=['Variable','Definition','Unit','Transform','Run field'],
                         notes=['Definitions follow the research materials and explicit mappings; unknown values remain unknown.'])
            for row, v in zip(table['rows'], c['variables']):
                row[:] = [v['label'],v['definition'] or 'Not provided',v['unit'] or 'Not provided',
                          v['transform'] or 'Not provided','; '.join(r+':'+f for r,f in v['members'].items())]
        elif table['kind'] == 'descriptive':
            n = [t for t in display['tables'] if t['kind'] == 'descriptive'].index(table)+1
            table.update(title=f'Model ({n}): descriptive statistics for the estimation sample',
                         header=['Field','N','Mean','SD','Min','Median','Max'],
                         notes=['These statistics refer only to this model\'s actual estimation sample.'])
            for row in table['rows']:
                row[1:] = ['Not provided' if v == '未提供' else v for v in row[1:]]
    paragraphs = []
    labels = dict(y='dependent variable',x='regressors',fixed_effects='fixed effects',standard_errors='standard errors',entity='entity field',time='time field')
    for d in c['differences']:
        paragraphs.append(f'{d["left"]} vs {d["right"]}: {d["intersection_count"]} shared observations; '
                          f'{len(d["left_only"])} only in the former and {len(d["right_only"])} only in the latter. '
                          f'Data version: {"different" if d["input_changed"] else "same"}. Changed settings: '+
                          (', '.join(labels[k] for k in d['changed_settings']) or 'none')+'.')
        for side in ('left_only_reasons','right_only_reasons'):
            info = d[side]
            for e in info['evidence']:
                rule=e['rule']
                if 'complete_case' in rule: desc='exclude missing '+rule['complete_case']
                else: desc=rule['field']+' '+rule['op']+' '+str(rule['value'])
                paragraphs.append(f'Run {e["source_run"]["id"]}: rule "{desc}" explains {len(e["keys"])} excluded observations.')
            if info['unresolved_keys']:
                paragraphs.append(f'Exclusion reasons remain unresolved for {len(info["unresolved_keys"])} observations.')
    if any(d['input_changed'] for d in c['differences']):
        paragraphs.append('Identifier systems and observational units require verification across data versions; matching text keys alone do not establish entity identity.')
    if c['differences']:
        paragraphs.append('When the model and sample both change, coefficient changes cannot be attributed solely to new controls. Numerical checks do not establish causality.')
    else:
        paragraphs.append('Numerical checks do not establish causality.')
    display['paragraphs'] = paragraphs
    display['sources'] = [f'({i+1}) {m["run"]["id"]} v{m["run"]["version"]}; plan {m["plan"]["id"]} v{m["plan"]["version"]}; input SHA-256 {m["input_sha256"]}' for i,m in enumerate(c['models'])]
    return display
