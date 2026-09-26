(() => {
  'use strict';
  const explorer = document.querySelector('.workflow-explorer');
  const cards = [...explorer.querySelectorAll('.feature-card')];
  const tablist = explorer.querySelector('.workflow-tabs');
  const visual = explorer.querySelector('.workflow-visual');
  const position = explorer.querySelector('.workflow-position');
  const controls = explorer.querySelector('.workflow-controls');
  const preview = (name, body, label = '材料示意') => `<div class="stage-preview"><div class="stage-preview-top"><span>${name}</span><span>${label}</span></div>${body}</div>`;
  const visuals = [
    preview('研究路线', '<img src="assets/research-routes-macos.jpg" width="960" height="600" alt="两条候选研究路线与数据概览">', '合成示例 · 讨论草案'),
    preview('从文献到自己的问题', '<div class="stage-note-body"><strong>每个研究选择，都有来处。</strong><p>把概念、测量和适用范围放在一起核对。</p><div class="evidence-links"><span>文献定义</span><i>→</i><span>候选指标</span><i>→</i><span>数据字段</span></div><div class="stage-tags"><span>来源</span><span>适用范围</span><span>待核实</span></div></div>'),
    preview('看清实际分析样本', '<div class="stage-note-body"><div class="stage-metrics"><div><b>72</b><span>分析观测</span></div><div><b>12</b><span>研究主体</span></div></div><p>来自当前合成示例报告。每次分析都需要检查自己的样本变化。</p><div class="stage-tags"><span>缺失与重复</span><span>变量口径</span><span>处理记录</span></div></div>', '合成示例'),
    preview('实际分析与数值复核', '<img src="assets/analysis-report-macos.jpg" width="960" height="600" alt="固定效应分析结果、样本与系数区间">', '合成示例 · 实际报告'),
    preview('整理为论文式表格', '<img src="assets/latex-report.png" width="834" height="1179" alt="实际生成的三模型论文表格">', '合成示例 · 实际 PDF'),
    preview('下次，从有效记录继续', '<div class="stage-note-body"><strong>我的研究项目</strong><div class="stage-files"><span>研究进展.md · 问题、进展与下一步</span><span>literature / · 材料与证据</span><span>data / · 原始值与处理产物</span><span>research / · 方案、运行与报告</span></div></div>', '文件结构示意')
  ];
  let activeStage = 0;

  const tabs = cards.map((card, index) => {
    const label = card.querySelector('.feature-index').textContent.split(' / ')[1];
    const tab = document.createElement('button');
    tab.type = 'button';
    tab.className = 'workflow-tab';
    tab.id = `workflow-tab-${index}`;
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-controls', `workflow-panel-${index}`);
    tab.innerHTML = `<span>0${index + 1}</span>${label}`;
    card.id = `workflow-panel-${index}`;
    card.setAttribute('role', 'tabpanel');
    card.setAttribute('aria-labelledby', tab.id);
    card.tabIndex = 0;
    const use = document.createElement('button');
    use.type = 'button';
    use.className = 'stage-use';
    use.innerHTML = '从这个问题开始 <svg aria-hidden="true"><use href="#i-arrow"/></svg>';
    use.addEventListener('click', () => {
      const prompt = document.querySelector('#starter-prompt');
      prompt.textContent = card.querySelector('.example-question').textContent.replace(/[“”]/g, '');
      document.querySelector('#copy-status').textContent = '';
      document.querySelector('#copy-prompt span').textContent = '复制';
      document.querySelector('#start').scrollIntoView({ behavior: 'smooth' });
      document.querySelector('#copy-prompt').focus({ preventScroll: true });
    });
    card.append(use);
    tab.addEventListener('click', () => selectStage(index));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % cards.length;
      if (event.key === 'ArrowLeft') next = (index + cards.length - 1) % cards.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = cards.length - 1;
      if (next === undefined) return;
      event.preventDefault();
      tabs[next].focus();
      selectStage(next);
    });
    tablist.append(tab);
    return tab;
  });

  function selectStage(index) {
    activeStage = index;
    tabs.forEach((tab, i) => {
      tab.setAttribute('aria-selected', String(i === index));
      tab.tabIndex = i === index ? 0 : -1;
      cards[i].hidden = i !== index;
    });
    visual.innerHTML = visuals[index];
    position.textContent = `0${index + 1} / 06`;
    visual.getAnimations?.().forEach(animation => animation.cancel());
    visual.animate?.([{ opacity: .25, transform: 'translateY(9px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 380, easing: 'cubic-bezier(.2,.7,.2,1)' });
  }
  explorer.dataset.enhanced = 'true';
  [tablist, visual, controls].forEach(element => { element.hidden = false; });
  selectStage(0);
  explorer.querySelector('.stage-next').addEventListener('click', () => {
    selectStage((activeStage + 1) % cards.length);
    tabs[activeStage].focus({ preventScroll: true });
  });

  const chartElement = document.querySelector('#coefficient-chart');
  const chartPanel = document.querySelector('.evidence-plot');
  const buttons = [...document.querySelectorAll('[data-coefficient]')];
  // Read the visible source-aligned table so the chart and numerical fallback agree.
  const data = [...document.querySelectorAll('.coefficient-fallback tbody tr')].map(row => {
    const cells = [...row.children].map(cell => cell.textContent);
    return { name: cells[0], estimate: +cells[1], lower: +cells[2], upper: +cells[3], text: cells };
  });
  let selected = 0;
  let chart;
  function selectCoefficient(index) {
    selected = index;
    const value = data[index];
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.coefficient === value.name)));
    document.querySelector('.estimate-label').textContent = `${value.name} · 系数估计`;
    document.querySelector('.estimate-value').textContent = value.text[1];
    document.querySelector('.estimate-interval').textContent = `95% 区间 [${value.text[2]}, ${value.text[3]}]`;
    document.querySelector('.estimate-note').textContent = `在这一合成样本与模型设定下，${value.name} 与结果变量呈正向条件关联。`;
    renderChart();
  }
  buttons.forEach(button => button.addEventListener('click', () => selectCoefficient(data.findIndex(value => value.name === button.dataset.coefficient))));

  function renderChart() {
    if (!chart) return;
    chart.setOption({
      animationDuration: 650,
      animationDurationUpdate: 350,
      backgroundColor: 'transparent',
      grid: { left: 35, right: 20, top: 35, bottom: 36 },
      xAxis: { type: 'value', min: 0, max: 1.5, interval: .5, axisLabel: { color: '#8391ae', fontSize: 11 }, splitLine: { lineStyle: { color: '#a6b2d412', type: 'dashed' } }, axisLine: { show: false }, axisTick: { show: false } },
      yAxis: { type: 'category', inverse: true, data: data.map(value => value.name), axisLabel: { color: '#c8cde1', fontSize: 14, margin: 18 }, axisLine: { show: false }, axisTick: { show: false } },
      tooltip: { trigger: 'item', backgroundColor: '#171d2e', borderColor: '#4b4967', textStyle: { color: '#e6e5f5', fontSize: 12 }, confine: true, formatter: params => {
        const value = data[params.dataIndex];
        return `${value.name} · ${value.text[1]}<br>95% 区间 [${value.text[2]}, ${value.text[3]}]`;
      } },
      series: [
        { type: 'custom', name: '95% 区间', renderItem: (params, api) => {
          const start = api.coord([api.value(1), api.value(0)]);
          const end = api.coord([api.value(2), api.value(0)]);
          const color = params.dataIndex === selected ? '#b6a4ff' : '#576a90';
          return { type: 'group', children: [
            { type: 'line', shape: { x1: start[0], y1: start[1], x2: end[0], y2: end[1] }, style: { stroke: color, lineWidth: 3 } },
            ...[start, end].map(point => ({ type: 'line', shape: { x1: point[0], y1: point[1] - 7, x2: point[0], y2: point[1] + 7 }, style: { stroke: color, lineWidth: 2 } }))
          ] };
        }, encode: { x: [1, 2], y: 0 }, data: data.map((value, index) => [index, value.lower, value.upper]), z: 1 },
        { type: 'scatter', name: '系数估计', symbolSize: 14, data: data.map((value, index) => ({ value: [value.estimate, index], itemStyle: { color: index === selected ? '#d0c4ff' : '#7995c1', opacity: 1, borderColor: '#111626', borderWidth: 3, shadowBlur: index === selected ? 18 : 0, shadowColor: '#9d86ff77' } })), emphasis: { scale: 1.3 }, z: 2 }
      ]
    });
  }
  function loadChart() {
    const script = document.createElement('script');
    script.src = 'vendor/echarts-5.6.0.min.js';
    script.onload = () => {
      try {
        chartPanel.classList.add('chart-ready');
        chart = window.echarts.init(chartElement, null, { renderer: 'svg' });
        renderChart();
        chart.on('click', params => { if (Number.isInteger(params.dataIndex)) selectCoefficient(params.dataIndex); });
        if ('ResizeObserver' in window) new ResizeObserver(() => chart.resize()).observe(chartElement);
        else addEventListener('resize', () => chart.resize(), { passive: true });
      } catch {
        chart?.dispose();
        chart = null;
        chartPanel.classList.remove('chart-ready');
      }
    };
    // The HTML table and variable controls remain usable if this asset cannot load.
    script.onerror = () => chartPanel.classList.remove('chart-ready');
    document.head.append(script);
  }
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect();
      loadChart();
    }, { rootMargin: '240px' });
    observer.observe(chartPanel);
  } else loadChart();
})();
