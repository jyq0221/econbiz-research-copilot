"""Independent source-text checks and strict reads of versioned LaTeX outputs."""

import json
from pathlib import Path
from .files import read_verified
from .latex_syntax import arguments, decode_text
from .state import WorkflowError


def check_latex_content(files, content):
    d=content['display']; en=content['language']=='en'
    checks=[]
    try:
        actual=[decode_text(v) for v in arguments(files['tables.tex'],'EBCell')]
        expected=[]
        for table in d['tables']:
            expected.extend(table['header']); expected.extend(table['header'])
            expected.extend(str(v) for row in table['rows'] for v in row)
        checks.append(dict(name='actual_cells_in_order',passed=actual==expected))
        headings=[]
        for table in d['tables']:
            headings += [table['title']]+[('Note: ' if en else '注：')+n for n in table['notes']]
        for name,values in [('tables.tex',headings),('narrative.tex',d['paragraphs']),
                            ('sources.tex',[('Generated: ' if en else '生成时间：')+content['generated_at']]+d['sources']),
                            ('equations.tex',[v for e in content['equations'] for v in (e['title'],e['explanation'])])]:
            checks.append(dict(name=name+'_text',passed=[decode_text(v) for v in arguments(files[name],'EBText')]==values))
        import re
        actual_math=re.findall(r'\\begin\{equation\}\n(.*?)\n\\end\{equation\}',files['equations.tex'],re.S)
        checks.append(dict(name='actual_equations',passed=actual_math==[e['latex'] for e in content['equations']]))
        # Canonical layout additionally rejects inserted commands, altered macro definitions
        # or omitted inputs. Numeric/text checks above do not rely on re-rendering.
        from .latex_report import render_latex
        checks.append(dict(name='layout_and_source_structure',passed=files==render_latex(content)))
    except (KeyError,TypeError,ValueError,WorkflowError):
        checks.append(dict(name='parseable_source',passed=False))
    return dict(status='passed' if all(c['passed'] for c in checks) else 'failed',checks=checks,
                scope='实际源文件单元格、文字、公式及受管结构；不认证自由文字或公式的研究含义')


def artifact_files(workspace, artifact, record_name):
    files={}
    for ref in artifact['files']:
        name=Path(ref['path']).name
        if name in files: raise WorkflowError('交付文件名称重复')
        files[name]=read_verified(workspace.root,ref)
    try:
        if json.loads(files[record_name])!=artifact['content']:
            raise WorkflowError('交付记录与登记材料不一致')
    except (KeyError,ValueError,TypeError) as exc:
        raise WorkflowError('交付记录损坏') from exc
    return files


def read_latex_report(workspace, report_id):
    from .latex_report import TEX_NAMES, resolve_content
    a=workspace.project.require_usable(report_id)
    if a['kind']!='latex_report': raise WorkflowError('需要 LaTeX 源文件交付')
    try:
        c=a['content']; files=artifact_files(workspace,a,'delivery.json')
        if set(files)!=set(TEX_NAMES)|{'README.md','delivery.json'}:
            raise WorkflowError('LaTeX 交付文件集合不符')
        rebuilt,_=resolve_content(workspace,comparison_id=c['comparison_id'],run_id=c['run_id'],
            narrative_id=c['narrative']['id'] if c['narrative'] else None,
            equations=c['equations'],language=c['language'],generated_at=c['generated_at'])
        if any(c[k]!=v for k,v in rebuilt.items()): raise WorkflowError('LaTeX 来源或展示版本不一致')
        import hashlib
        if c['source_files']!=[dict(name=n,sha256=hashlib.sha256(files[n]).hexdigest()) for n in TEX_NAMES]:
            raise WorkflowError('源文件散列不一致')
        checked=check_latex_content({n:files[n].decode('utf-8') for n in TEX_NAMES},c)
        if checked['status']!='passed' or checked!=c['source_check']:
            raise WorkflowError('LaTeX 实际内容核对未通过')
        return a
    except (KeyError,ValueError,TypeError,AttributeError) as exc:
        raise WorkflowError('LaTeX 交付记录损坏：'+str(exc)) from exc


def read_latex_build(workspace, build_id):
    from .latex_runtime import pdf_page_count, log_warnings
    import hashlib
    a=workspace.project.artifact(build_id)
    if a['kind']!='latex_build': raise WorkflowError('需要 LaTeX 编译记录')
    try:
        c=a['content']; files=artifact_files(workspace,a,'build.json')
        if not {'compile.log','build.json'}<=set(files) or set(files)-{'compile.log','build.json','report.pdf','report.aux'}:
            raise WorkflowError('编译证据文件集合不符')
        if log_warnings(files['compile.log'].decode('utf-8'))!=c['warnings']:
            raise WorkflowError('编译警告与实际日志不符')
        if c['compile_check']=='failed':
            if a['execution_status'] not in {'failed','stale'} or not c['error'] or c['pdf_sha256'] is not None or 'report.pdf' in files:
                raise WorkflowError('失败编译记录与实际状态不符')
            return a
        if c['compile_check']!='passed': raise WorkflowError('未知编译状态')
        workspace.project.require_usable(build_id)
        report=read_latex_report(workspace,c['report']['id'])
        if (report['version']!=c['report']['version'] or report['content']['source_files']!=c['report']['source_files']):
            raise WorkflowError('PDF 对应源文件已变更')
        if (c['error'] is not None or c['passes'] not in (2,3) or c['exit_codes']!=[0]*c['passes'] or
                not c['engine']['version'].startswith('XeTeX ') or c['visual_check']!='not_performed' or
                '-no-shell-escape' not in c['options'] or pdf_page_count(files['report.pdf'])!=c['page_count'] or
                hashlib.sha256(files['report.pdf']).hexdigest()!=c['pdf_sha256']):
            raise WorkflowError('PDF 编译记录与实际证据不一致')
        return a
    except (KeyError,ValueError,TypeError,AttributeError) as exc:
        raise WorkflowError('LaTeX 编译记录损坏：'+str(exc)) from exc


def _check_pages(raw_pages, count, inspected_pages, findings):
    from .state import require_text
    if (not isinstance(inspected_pages,list) or any(type(p) is not int for p in inspected_pages) or
            sorted(inspected_pages)!=list(range(1,count+1))):
        raise WorkflowError('须声明已逐页检查全部实际 PDF 页面')
    if not isinstance(findings,list): raise WorkflowError('视觉发现须为文本列表')
    for item in findings: require_text(item,'视觉发现')
    if list(raw_pages)!=[f'page-{i}.png' for i in range(1,count+1)]:
        raise WorkflowError('页图片须按 page-1.png 起连续排序，与实际 PDF 页数一致')
    try:
        from PIL import Image
        import io
        for raw in raw_pages.values():
            with Image.open(io.BytesIO(raw)) as im:
                if im.format!='PNG': raise ValueError('not PNG')
                im.verify()
    except ImportError as exc:
        raise WorkflowError('逐页检查需要 latex 可选依赖（Pillow）') from exc
    except Exception as exc:
        raise WorkflowError('页面图片损坏：'+str(exc)) from exc


def record_latex_review(workspace, review_id, build_id, *, pages, inspected_pages, findings, reason):
    from .files import describe_file
    from .state import now
    from .workspace import encode_json
    build=read_latex_build(workspace,build_id)
    c=build['content']
    if c['compile_check']!='passed': raise WorkflowError('失败编译不能进行版式验收')
    if not isinstance(pages,list): raise WorkflowError('页面路径须为列表')
    raw_pages={}
    for path in pages:
        name=Path(path).name
        if name in raw_pages: raise WorkflowError('页面路径重复')
        ref=describe_file(workspace.root,Path(path).absolute(),scope='external',role='latex_page')
        raw_pages[name]=read_verified(workspace.root,ref)
    _check_pages(raw_pages,c['page_count'],inspected_pages,findings)
    version=workspace._version_number(review_id)
    prefix=f'{workspace.layout["research_reports"]}/{review_id}/v{version:04d}'
    content=dict(build=dict(id=build_id,version=build['version']),pdf_sha256=c['pdf_sha256'],
                 page_count=c['page_count'],recorded_at=now(),inspected_pages=inspected_pages,findings=findings,
                 render_check='passed',visual_check='failed' if findings else 'passed',
                 scope='PDF及页图片字节已核对；逐页观察由调用者声明，不认证观察者身份或像素对应关系')
    writes=[(prefix+'/'+n,raw) for n,raw in raw_pages.items()]+[(prefix+'/review.json',encode_json(content))]
    files=[workspace._file(p,b,'latex_review') for p,b in writes]
    staged=workspace._stage(review_id,'latex_review',content,[build_id],files,reason)
    staged.mark(review_id,'completed','passed','页面检查证据已保存；视觉结论单独记录')
    workspace._publish(staged,writes)
    return workspace.project.artifact(review_id)


def read_latex_review(workspace, review_id):
    a=workspace.project.require_usable(review_id)
    if a['kind']!='latex_review': raise WorkflowError('需要 LaTeX 逐页检查记录')
    try:
        c=a['content'];files=artifact_files(workspace,a,'review.json')
        b=read_latex_build(workspace,c['build']['id'])
        if (b['content']['compile_check']!='passed' or b['version']!=c['build']['version'] or
                b['content']['pdf_sha256']!=c['pdf_sha256'] or b['content']['page_count']!=c['page_count']):
            raise WorkflowError('检查所对应 PDF 已变化')
        pages={n:v for n,v in files.items() if n!='review.json'}
        _check_pages(pages,c['page_count'],c['inspected_pages'],c['findings'])
        if c['render_check']!='passed' or c['visual_check']!=('failed' if c['findings'] else 'passed'):
            raise WorkflowError('页面检查状态与证据不符')
        return a
    except (KeyError,TypeError,ValueError,AttributeError) as exc:
        raise WorkflowError('LaTeX 逐页检查记录损坏：'+str(exc)) from exc
