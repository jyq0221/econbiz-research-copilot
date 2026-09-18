"""Bounded native XeLaTeX attempts, frozen inputs and separately checked PDF output."""

import hashlib
import io
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from .files import read_verified
from .processes import run_process
from .state import WorkflowError, now
from .workspace import Workspace, encode_json, require_id


def pdf_page_count(raw):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise WorkflowError('PDF 检查需要 latex 可选依赖（pypdf）') from exc
    try:
        pdf=PdfReader(io.BytesIO(raw),strict=True)
        if pdf.is_encrypted: raise ValueError('encrypted PDF')
        count=len(pdf.pages)
        if not count: raise ValueError('empty PDF')
        return count
    except Exception as exc:
        raise WorkflowError('本次 PDF 无法解析：'+str(exc)) from exc


def log_warnings(log):
    markers=('Missing character:', 'Overfull \\hbox', 'Overfull \\vbox', 'undefined references',
             'undefined on input', 'Rerun to get', 'Label(s) may have changed', 'Table widths have changed')
    return list(dict.fromkeys(line.strip() for line in log.splitlines() if any(m in line for m in markers)))


def _unstable(log):
    return any(s in log for s in ('Rerun to get','Label(s) may have changed','Table widths have changed'))


def compile_latex_report(workspace, build_id, report_id, *, executable=None, timeout=120):
    from .latex_checks import read_latex_report
    from .latex_report import TEX_NAMES
    require_id(build_id)
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout<=0:
        raise WorkflowError('编译时限须为有限正数')
    if build_id==report_id: raise WorkflowError('编译和源文件须使用不同标识')
    report=read_latex_report(workspace,report_id)
    refs={Path(f['path']).name:f for f in report['files']}
    inputs={name:read_verified(workspace.root,refs[name]) for name in TEX_NAMES}
    source_ref=dict(id=report_id,version=report['version'],source_files=report['content']['source_files'])
    initial_state=workspace.project.snapshot()
    started=now(); deadline=time.monotonic()+timeout
    info=dict(path=None,version=None); passes=0; codes=[]; error=None; warnings=[]
    pdf=None; pages=None; logs=[]; aux=None
    options=['-no-shell-escape','-interaction=nonstopmode','-halt-on-error','-file-line-error','-jobname=report','main.tex']
    with tempfile.TemporaryDirectory(prefix='econbiz-latex-') as directory:
        root=Path(directory)
        for name,raw in inputs.items(): (root/name).write_bytes(raw)
        try:
            path=shutil.which('xelatex') if executable is None else str(Path(executable).expanduser().absolute())
            if not path or not Path(path).is_file() or not os.access(path,os.X_OK):
                raise WorkflowError('未找到可执行的 XeLaTeX；源文件已保留')
            # Keep the xelatex symlink name: resolving it would invoke xetex without its format.
            info['path']=str(Path(path).absolute())
            env=dict(os.environ,PATH=str(Path(path).parent)+os.pathsep+os.environ.get('PATH',''),
                     openin_any='p',openout_any='p',TEXMFOUTPUT=directory)
            version=run_process([path,'--version'],cwd=directory,env=env,timeout=max(.001,min(10,deadline-time.monotonic())))
            info['version']=version.stdout.strip()
            if version.returncode or not info['version'].startswith('XeTeX '):
                raise WorkflowError('编译程序未识别为 XeTeX')
            previous=None
            for passes in range(1,4):
                remaining=deadline-time.monotonic()
                if remaining<=0: raise subprocess.TimeoutExpired(path,timeout)
                result=run_process([path]+options,cwd=directory,env=env,timeout=remaining,
                                   log_path=str(root/f'pass-{passes}.txt'))
                codes.append(result.returncode)
                if result.returncode: raise WorkflowError(f'XeLaTeX 第 {passes} 遍失败，退出码 {result.returncode}')
                raw_aux=(root/'report.aux').read_bytes() if (root/'report.aux').exists() else b''
                log=(root/'report.log').read_text(errors='replace') if (root/'report.log').exists() else ''
                digest=hashlib.sha256(raw_aux).hexdigest()
                if passes>=2 and digest==previous and not _unstable(log):
                    aux=raw_aux;break
                previous=digest
            else:
                raise WorkflowError('三遍编译后辅助文件或交叉引用仍未稳定')
            output=root/'report.pdf'
            if not output.is_file(): raise WorkflowError('本次编译未生成 PDF')
            pdf=output.read_bytes(); pages=pdf_page_count(pdf)
        except (OSError,ValueError,subprocess.SubprocessError) as exc:
            error=('编译超时：'+str(timeout)+' 秒' if isinstance(exc,subprocess.TimeoutExpired) else str(exc))
            pdf=None;pages=None
        finally:
            for f in sorted(root.glob('pass-*.txt')):
                logs.append(f.name+'\n'+f.read_text(errors='replace'))
            if (root/'report.log').exists(): logs.append('report.log\n'+(root/'report.log').read_text(errors='replace'))
            warnings=log_warnings('\n'.join(logs))
    # Re-read authoritative state after the subprocess; do not overwrite edits made
    # during compilation, even when they concern an unrelated record.
    fresh=Workspace.open(workspace.root)
    if fresh.project.snapshot()!=initial_state:
        workspace.project=fresh.project
    try:
        current=read_latex_report(workspace,report_id)
        if (current['version']!=source_ref['version'] or current['content']['source_files']!=source_ref['source_files']):
            raise WorkflowError('编译期间源文件版本发生变化')
    except WorkflowError as exc:
        error='编译收尾来源核对失败：'+str(exc);pdf=None;pages=None
    compile_check='failed' if error else 'passed'
    content=dict(report=source_ref,engine=info,options=options,started_at=started,finished_at=now(),
                 passes=passes,exit_codes=codes,compile_check=compile_check,visual_check='not_performed',
                 page_count=pages,pdf_sha256=hashlib.sha256(pdf).hexdigest() if pdf else None,
                 warnings=warnings,error=error)
    version=workspace._version_number(build_id)
    prefix=f'{workspace.layout["research_reports"]}/{build_id}/v{version:04d}'
    log='\n\n'.join(logs)+('\nERROR: '+error if error else '')+'\n'
    writes=[(prefix+'/compile.log',log.encode('utf-8'))]
    if pdf: writes.append((prefix+'/report.pdf',pdf))
    if aux is not None: writes.append((prefix+'/report.aux',aux))
    writes.append((prefix+'/build.json',encode_json(content)))
    files=[workspace._file(p,b,'latex_build') for p,b in writes]
    staged=workspace._stage(build_id,'latex_build',content,[] if error else [report_id],files,'记录 XeLaTeX 编译尝试')
    staged.mark(build_id,'failed' if error else 'completed',compile_check,'编译结果与实际 PDF 结构检查')
    workspace._publish(staged,writes)
    return workspace.project.artifact(build_id)
