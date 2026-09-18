(() => {
  'use strict';
  const previews = {
    analysis: { image: 'assets/analysis-report-macos.jpg', title: '分析结果 · 报告展示版', alt: '分析结果展示版：72 个合成观测、12 个主体及系数区间图', description: '实际执行的 Python 分析 · 独立数值复核通过', source: 'examples/analysis-report.html', link: '查看原始报告' },
    routes: { image: 'assets/research-routes-macos.jpg', title: '研究路线 · 报告展示版', alt: '研究路线展示版：数据概览及两条候选路线', description: '基于实际报告重排 · 讨论草案', source: 'examples/research-routes.html', link: '查看原始报告' },
    report: { image: 'assets/latex-report.png', title: 'LaTeX 结果导出 · 合成数据示例', alt: '实际 PDF 报告页面，包含多模型三线表、变量定义与同样本描述统计', description: '实际生成的 PDF · 三模型排版示例', source: 'examples/latex-report.pdf', link: '打开原始 PDF' }
  };
  const tabs = [...document.querySelectorAll('[data-preview]')];
  const panel = document.querySelector('#preview-panel');
  const screenshot = document.querySelector('#hero-screenshot');
  const imageButton = document.querySelector('.preview-image-button');
  const description = document.querySelector('#preview-description');
  const source = document.querySelector('#preview-source');
  const dialog = document.querySelector('.image-dialog');
  let activePreview = 'analysis';

  function selectPreview(tab) {
    activePreview = tab.dataset.preview;
    const preview = previews[activePreview];
    tabs.forEach(item => { item.setAttribute('aria-selected', String(item === tab)); item.tabIndex = item === tab ? 0 : -1; });
    panel.setAttribute('aria-labelledby', tab.id);
    screenshot.src = preview.image;
    screenshot.alt = preview.alt;
    screenshot.width = activePreview === 'report' ? 834 : 960;
    screenshot.height = activePreview === 'report' ? 1179 : 600;
    imageButton.classList.toggle('paper', activePreview === 'report');
    imageButton.setAttribute('aria-label', `放大${preview.title}`);
    description.replaceChildren();
    const check = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', '#i-check'); check.append(use);
    description.append(check, document.createTextNode(preview.description));
    source.href = preview.source;
    source.firstChild.textContent = `${preview.link} `;
    if (document.documentElement.dataset.motion === 'running' && screenshot.animate) {
      screenshot.getAnimations().forEach(animation => animation.cancel());
      screenshot.animate([{ opacity: .45, transform: 'translateY(5px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 320, easing: 'ease-out' });
    }
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectPreview(tab));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next === undefined) return;
      event.preventDefault(); tabs[next].focus(); selectPreview(tabs[next]);
    });
  });

  function showImage(image, title) {
    document.querySelector('#dialog-title').textContent = title;
    const fullImage = document.querySelector('#dialog-image');
    fullImage.src = image; fullImage.alt = title;
    dialog.showModal();
  }
  function expandPreview() { const preview = previews[activePreview]; showImage(preview.image, preview.title); }
  imageButton.addEventListener('click', expandPreview);
  document.querySelector('.preview-expand').addEventListener('click', expandPreview);
  document.querySelectorAll('[data-image]').forEach(button => button.addEventListener('click', () => showImage(button.dataset.image, button.dataset.title)));
  document.querySelector('#dialog-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close(); } });

  const menu = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#navigation');
  function closeMenu() { menu.setAttribute('aria-expanded', 'false'); menu.setAttribute('aria-label', '打开导航'); nav.classList.remove('open'); }
  menu.addEventListener('click', () => { const open = menu.getAttribute('aria-expanded') !== 'true'; menu.setAttribute('aria-expanded', String(open)); menu.setAttribute('aria-label', open ? '关闭导航' : '打开导航'); nav.classList.toggle('open', open); });
  nav.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') { closeMenu(); menu.focus(); } });

  document.querySelector('#copy-prompt').addEventListener('click', async () => {
    const status = document.querySelector('#copy-status');
    const prompt = document.querySelector('#starter-prompt');
    try {
      await navigator.clipboard.writeText(prompt.textContent);
      status.textContent = '已复制。打开项目后，粘贴给你的研究助手即可。';
      document.querySelector('#copy-prompt span').textContent = '已复制';
    } catch {
      const range = document.createRange(); range.selectNodeContents(prompt);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      status.textContent = '文字已选中，请用系统的复制功能复制。';
    }
  });
})();
