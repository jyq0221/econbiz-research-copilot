"""Versioned LaTeX delivery from checked models, without new estimation."""

from .comparison import read_model_comparison
from .comparison_input import load_checked_model
from .comparison_display import build_display
from .latex_syntax import escape_text, validate_math
from .state import WorkflowError, now, require_text, json_copy
from .workspace import encode_json, require_id

TEX_NAMES = ('main.tex', 'tables.tex', 'narrative.tex', 'equations.tex', 'sources.tex')


def resolve_content(workspace, *, comparison_id, run_id, narrative_id, equations, language, generated_at):
    if language not in ('zh-CN', 'en') or (comparison_id is None) == (run_id is None):
        raise WorkflowError('指定一个运行或比较来源，语言为 zh-CN 或 en')
    en = language == 'en'
    source_id = comparison_id if comparison_id is not None else run_id
    require_id(source_id)
    if comparison_id is not None:
        artifact = read_model_comparison(workspace, comparison_id)
        data = artifact['content']
    else:
        model = load_checked_model(workspace, run_id)
        artifact = workspace.project.artifact(run_id)
        variables = [dict(id='v'+str(i), label=f, definition=v['definition'], unit=v['unit'],
                          transform=v['transform'], members={run_id:f}, evidence_refs=[])
                     for i,(f,v) in enumerate(model['variables'].items())]
        data = dict(title='Regression results' if en else '回归结果', created_at=generated_at,
                    models=[dict(model,title=run_id,role='other')], variables=variables,
                    stars=[], display_terms=None, differences=[])
    display = build_display(data)
    if en:
        from .comparison_english import english_display
        display = english_display(display, data)
    elif comparison_id is None:
        display['paragraphs'] = ['数值核验不认证因果关系。']
    deps = [source_id]
    narrative = None
    if narrative_id is not None:
        a = workspace.project.require_usable(narrative_id)
        if a['kind'] != 'session_note': raise WorkflowError('结果说明须引用有效研究笔记')
        narrative = dict(id=narrative_id,version=a['version'])
        display['paragraphs'].append(('Research note: ' if en else '研究说明：')+a['content']['summary'])
        deps.append(narrative_id)
    equations = [] if equations is None else json_copy(equations)
    if not isinstance(equations,list): raise WorkflowError('公式须为列表')
    ids = set()
    for eq in equations:
        if not isinstance(eq,dict) or set(eq) != {'id','title','latex','explanation','source_refs'}:
            raise WorkflowError('公式字段不完整')
        require_id(eq['id'])
        if eq['id'] in ids: raise WorkflowError('公式标识重复')
        ids.add(eq['id'])
        for k in ('title','explanation'): require_text(eq[k], k)
        validate_math(eq['latex'])
        if not isinstance(eq['source_refs'],list) or not eq['source_refs']:
            raise WorkflowError('公式必须引用当前方案或研究笔记')
        for ref in eq['source_refs']:
            if not isinstance(ref,dict) or set(ref) != {'artifact_id','version'}:
                raise WorkflowError('公式来源引用不完整')
            a = workspace.project.require_usable(ref['artifact_id'])
            if a['kind'] not in {'plan','session_note'} or type(ref['version']) is not int or a['version'] != ref['version']:
                raise WorkflowError('公式来源种类或版本无效')
            deps.append(a['id'])
            display['sources'].append(('Equation ' if en else '公式 ')+eq['id']+': '+a['id']+' v'+str(a['version']))
    display['sources'].append(('Source ' if en else '来源 ')+source_id+' v'+str(artifact['version']))
    if narrative:
        display['sources'].append(('Research note ' if en else '研究笔记 ')+narrative_id+' v'+str(narrative['version']))
    content = dict(source=dict(id=source_id,version=artifact['version'],kind=artifact['kind']),
                   comparison_id=comparison_id,run_id=run_id,narrative=narrative,
                   language=language,equations=equations,generated_at=generated_at,display=display,
                   compile_check='not_performed',visual_check='not_performed')
    return content, list(dict.fromkeys(deps))


def _text(value):
    return r'\EBText{'+escape_text(value)+'}'


def render_latex(content):
    d=content['display']; en=content['language']=='en'
    tables=[]
    for i,t in enumerate(d['tables']):
        wide=t['kind']=='models' and len(t['header'])>4
        n=len(t['header']); usable=261 if wide else 174
        widths = ([35,49,16,25,49] if t['kind']=='definitions' else
                  [36]+[(usable-36)/(n-1)]*(n-1))
        widths=[w-2.12 for w in widths]
        columns=''.join(r'>{\raggedright\arraybackslash}p{'+f'{w:.2f}mm'+'}' for w in widths)
        row=lambda cells: ' & '.join(r'\EBCell{'+escape_text(str(v))+'}' for v in cells)+r' \\'
        tables.append(f'% EB-TABLE {i}')
        if wide: tables.append(r'\begin{landscape}')
        if i == 0: tables.append(r'\EBReportHeading')
        span = r'\multicolumn{'+str(n)+r'}{p{'+f'{usable-2.12:.2f}mm'+r'}}{'
        tables += [r'{\small',r'\begin{longtable}{'+columns+'}',
                   span+r'\large\bfseries '+_text(t['title'])+r'} \\[3mm]',
                   r'\toprule', row(t['header']),r'\midrule\endfirsthead',r'\toprule',row(t['header']),
                   r'\midrule\endhead',r'\bottomrule\endfoot',r'\bottomrule']
        tables += [span+_text(('Note: ' if en else '注：')+note)+r'} \\' for note in t['notes']]
        tables.append(r'\endlastfoot')
        tables += [row(r) for r in t['rows']]
        tables += [r'\end{longtable}', '}']
        if wide: tables.append(r'\end{landscape}')
    eqs=[]
    for eq in content['equations']:
        eqs += [r'\subsection*{'+_text(eq['title'])+'}', '% EB-EQUATION '+eq['id'],
                r'\begin{equation}',eq['latex'],r'\end{equation}',_text(eq['explanation'])+r'\par']
    preamble = r'''\documentclass[UTF8,fontset=fandol,scheme=plain,10pt,a4paper]{ctexart}
\usepackage[margin=18mm]{geometry}
\usepackage{amsmath,amssymb,booktabs,longtable,array,pdflscape}
\setlength{\tabcolsep}{3pt}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}
\setlength{\emergencystretch}{3em}
\renewcommand{\arraystretch}{1.22}
\newcommand{\EBText}[1]{#1}
\newcommand{\EBCell}[1]{#1}
\newcommand{\EBBreak}{\newline}
\newcommand{\EBTab}{\hspace{2em}}
\newcommand{\EBReturn}{\space}
\begin{document}
'''
    intro = ('This report presents checked regression results, sample information and variable definitions.' if en else
             '本报告整理已核验回归结果、实际样本与变量定义。')
    main = preamble+r'\newcommand{\EBReportHeading}{{\Large\bfseries '+_text(d['title'])+r'}\par '+_text(intro)+r'\par\medskip}'+'\n'
    main += '\\input{tables.tex}\n\\clearpage\n'
    main += r'\section*{'+_text('Results and specification' if en else '结果与设定说明')+'}\n\\input{narrative.tex}\n'
    if eqs: main += r'\section*{'+_text('Model equations' if en else '模型公式')+'}\n\\input{equations.tex}\n'
    main += r'\section*{'+_text('Sources and versions' if en else '来源与版本')+'}\n\\begingroup\\small\\setlength{\\parskip}{2pt}\n\\input{sources.tex}\n\\endgroup\n\\end{document}\n'
    sources=[('Generated: ' if en else '生成时间：')+content['generated_at']]+d['sources']
    return {'main.tex':main,'tables.tex':'\n'.join(tables)+'\n',
            'narrative.tex':'\n'.join(_text(p)+r'\par' for p in d['paragraphs'])+'\n',
            'equations.tex':'\n'.join(eqs)+'\n',
            'sources.tex':'\n'.join(_text(p)+r'\par' for p in sources)+'\n'}


def write_latex_report(workspace, report_id, *, comparison_id=None, run_id=None,
                       narrative_id=None, equations=None, language='zh-CN'):
    require_id(report_id)
    content,deps=resolve_content(workspace,comparison_id=comparison_id,run_id=run_id,narrative_id=narrative_id,
                                equations=equations,language=language,generated_at=now())
    texts=render_latex(content)
    from .latex_checks import check_latex_content
    check=check_latex_content(texts,content)
    if check['status']!='passed': raise WorkflowError('LaTeX 实际内容核对失败')
    content['source_check']=check
    version=workspace._version_number(report_id)
    prefix=f'{workspace.layout["research_reports"]}/{report_id}/v{version:04d}'
    writes=[(prefix+'/'+name,text.encode('utf-8')) for name,text in texts.items()]
    files=[workspace._file(p,b,'latex_source') for p,b in writes]
    content['source_files']=[dict(name=name,sha256=ref['sha256']) for name,ref in zip(texts,files)]
    readme=('Editable result snapshot. Compile main.tex with XeLaTeX (two or three passes).\n'
            'Required: ctex/Fandol, geometry, amsmath, amssymb, booktabs, longtable, array, pdflscape.\n'
            'tables.tex uses EBCell/EBText macros defined in main.tex. Copy their definitions when reusing tables.\n'
            'Use the project compile_latex_report interface to retain logs and version checks.\n'
            'Compilation does not establish visual review or causal validity.\n' if language=='en' else
            '可编辑结果快照。main.tex 使用 XeLaTeX 编译两至三遍。\n'
            '所需宏包：ctex/Fandol、geometry、amsmath、amssymb、booktabs、longtable、array、pdflscape。\n'
            '单独引用 tables.tex 时，请同时复制 main.tex 中 EBCell/EBText 等宏定义。\n'
            '使用项目 compile_latex_report 接口可保存日志和版本核对。编译通过不代表逐页检查或因果识别成立。\n')
    writes += [(prefix+'/README.md',readme.encode()),(prefix+'/delivery.json',encode_json(content))]
    files += [workspace._file(p,b,'latex_delivery_record') for p,b in writes[-2:]]
    staged=workspace._stage(report_id,'latex_report',content,deps,files,'导出已核验 LaTeX 结果')
    staged.mark(report_id,'completed','passed','源文件文字及数值核对通过；编译和视觉检查另记')
    workspace._publish(staged,writes)
    return workspace.project.artifact(report_id)
