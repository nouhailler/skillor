(() => {
  'use strict';
  const API_URL = (window.SKILLOR_API_URL || '').replace(/\/$/, '');
  const state = {dashboard:null, occupations:[], skills:[], trends:[], future:null, sources:[], quality:[], geographies:null, eurostat:[], series:[], searchFilters:{languages:[],sources:[]}};
  const $ = selector => document.querySelector(selector);
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const formatNumber = value => value == null ? '—' : new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1}).format(value);
  const formatDate = value => value ? new Intl.DateTimeFormat('fr-FR',{dateStyle:'medium'}).format(new Date(value)) : 'Jamais importé';
  const formatMetric = (value,unit='') => {
    if (value == null) return '—';
    const suffix = {'EUR/year':' €/an','EUR/month':' €/mois','EUR/hour':' €/h','percent':' %','score_0_100':' / 100','offer':' offres'}[unit] ?? (unit ? ` ${unit}` : '');
    return `${formatNumber(value)}${suffix}`;
  };
  const metricLabels = {job_offers:'Offres d’emploi',job_seekers:'Demandeurs d’emploi',hires:'Embauches',skill_offer_mentions:'Mentions de compétences',employment_by_sector:'Emploi par secteur',salary_average:'Salaire moyen',salary_min:'Salaire minimum',salary_max:'Salaire maximum',recruitment_difficulty:'Difficulté de recrutement',tension_index:'Indice de tension',tension_score:'Indice de tension',growth:'Croissance',unemployment_rate:'Taux de chômage',employment_rate:'Taux d’emploi'};
  const metricLabel = value => metricLabels[value] || String(value || '').replaceAll('_',' ');
  const relationshipLabel = value => ({essential:'Essentielle',optional:'Optionnelle'}[value] || value || 'Relation');
  const flattenLocalized = value => Object.entries(value || {}).flatMap(([language,terms]) => (Array.isArray(terms)?terms:[terms]).filter(Boolean).map(term=>({language,term})));
  const metricValue = (occupation, metric) => occupation.market?.[metric]?.value ?? null;
  const empty = message => `<div class="state">${escapeHtml(message)}</div>`;
  const errorState = message => `<div class="state error">${escapeHtml(message)}</div>`;
  const iconBrief = '<svg class="icon"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V4h8v3"/></svg>';
  let occupationReturnView='occupations';
  let skillReturnView='skills';
  let currentOccupation=null;

  async function apiGet(path) {
    const response = await fetch(API_URL + path, {headers:{Accept:'application/json'}});
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function hydrateShell() {
    $('#dashboard').innerHTML = `
      <div class="page-head"><div><div class="eyebrow">Observatoire connecté</div><h1>Le marché des compétences, en clair.</h1><p class="subtitle">Données issues de SQLite via FastAPI.</p></div><span class="demo-pill" id="dataStatus"><i></i>Chargement des données…</span></div>
      <div class="kpis" id="dashboardKpis">${empty('Chargement des indicateurs…')}</div>
      <div class="grid-main"><article class="card"><div class="card-head"><div><h2>Dynamique du marché</h2><div class="subtitle" id="seriesSubtitle">Série observée</div></div></div><div class="chart" id="marketChart">${empty('Chargement de la série…')}</div><div class="provenance"><span id="seriesProvenance">Source en cours de lecture</span><span class="quality">● Données observées</span></div></article><article class="card"><div class="card-head"><div><h2>Compétences en accélération</h2><div class="subtitle">TrendScore interne · 0–100</div></div><button class="link-btn" data-open-view="trends">Explorer</button></div><div class="rank-list" id="dashboardTrends">${empty('Chargement…')}</div></article></div>
      <div class="lower-grid"><article class="card"><div class="card-head"><div><h2>Métiers les plus demandés</h2><div class="subtitle">Offres rattachées sur les 12 dernières périodes mensuelles</div></div></div><div class="bars" id="topOccupations">${empty('Chargement…')}</div></article><article class="card"><div class="card-head"><div><h2>Métiers en hausse</h2><div class="subtitle">Évolution entre la première et la dernière période observée</div></div></div><div class="rank-list" id="occupationTrends">${empty('Chargement…')}</div></article></div>
      <div class="lower-grid"><article class="card"><div class="card-head"><div><h2>Salaires et tension</h2><div class="subtitle">Unités conservées, aucune conversion implicite</div></div></div><div id="marketSnapshot">${empty('Chargement…')}</div></article><article class="card"><div class="card-head"><div><h2>Fraîcheur des données</h2><div class="subtitle">Dernière synchronisation enregistrée par source</div></div></div><div id="dashboardUpdates">${empty('Chargement…')}</div></article></div>`;
    $('#occupations').innerHTML = `<div class="page-head"><div><div class="eyebrow">Référentiel ESCO</div><h1>Explorer les métiers</h1><p class="subtitle">Fiches, compétences et observations de marché réellement stockées.</p></div><span class="demo-pill" id="occupationCount"><i></i>Chargement…</span></div><div class="section-tools"><input id="occupationSearch" placeholder="Rechercher un métier…"/><div class="filters"><select class="filter" id="sectorFilter"><option value="">Tous les secteurs</option></select></div></div><div class="catalog-grid" id="occupationCards">${empty('Chargement des métiers…')}</div>`;
    $('#skills').innerHTML = `<div class="page-head"><div><div class="eyebrow">Référentiel de compétences</div><h1>Cartographie des compétences</h1><p class="subtitle">Relations ESCO et tendances calculées en base.</p></div><span class="demo-pill" id="skillCount"><i></i>Chargement…</span></div><div class="section-tools"><input id="skillSearch" placeholder="Rechercher une compétence…"/><div class="filters"><select class="filter" id="skillTypeFilter"><option value="">Tous les types</option><option value="skill">Compétence</option><option value="knowledge">Connaissance</option></select></div></div><div class="catalog-grid" id="skillCards">${empty('Chargement des compétences…')}</div>`;
    $('#trends').innerHTML = `<div class="page-head"><div><div class="eyebrow">Prospective × réalité observée</div><h1>Future of Jobs</h1><p class="subtitle">Projections documentaires comparées aux TrendScores observés, sans interprétation causale.</p></div><div class="filters"><select class="filter" id="futureEdition"><option value="">Aucune édition</option></select><button class="secondary" id="quadExport">Exporter CSV</button></div></div><article class="card"><div class="card-head"><div><h2>Centralité × progression projetée</h2><div class="subtitle" id="futureSubtitle">Axes et unités fournis par l'édition sélectionnée</div></div></div><div class="quadrant" id="trendQuadrant">${empty('Chargement des projections…')}</div><div class="provenance"><span id="futureSource">Source prospective</span><span class="quality">● Projection, pas mesure temps réel</span></div></article><article class="card" style="margin-top:13px"><div class="card-head"><div><h2>Projection / observations</h2><div class="subtitle">Écarts descriptifs uniquement</div></div></div><div id="futureComparison">${empty('Aucune comparaison disponible.')}</div></article>`;
    $('#compare').innerHTML = `<div class="page-head"><div><div class="eyebrow">Analyse croisée</div><h1>Comparer les métiers</h1><p class="subtitle">Comparaison des fiches et indicateurs réellement disponibles.</p></div></div><div class="compare-select" id="compareSelectors">${empty('Chargement des métiers…')}</div><article class="card compare-scroll" id="compareResult">${empty('Sélectionnez des métiers à comparer.')}</article>`;
    $('#geo').innerHTML = `<div class="page-head"><div><div class="eyebrow">Dynamiques territoriales</div><h1>Indicateurs par territoire</h1><p class="subtitle">France Travail lorsque disponible, sinon indicateur régional Eurostat.</p></div><span class="demo-pill" id="geoPeriod"><i></i>Chargement…</span></div><div class="filters" style="margin-bottom:16px"><select class="filter" id="geoMetric"><option value="job_offers">Offres France Travail</option><option value="regional_unemployment_rate">Chômage régional Eurostat</option></select></div><div class="geo-grid" id="geoCards">${empty('Chargement des territoires…')}</div>`;
    $('#sources').innerHTML = `<div class="page-head"><div><div class="eyebrow">Provenance & fraîcheur</div><h1>Sources de données</h1><p class="subtitle">État et qualité calculés directement depuis SQLite.</p></div><span class="demo-pill" id="sourceCount"><i></i>Chargement…</span></div><div class="sources-grid" id="sourceCards">${empty('Chargement des sources…')}</div><article class="card" style="margin-top:13px"><div class="card-head"><div><h2>ConfidenceScore observé</h2><div class="subtitle">Cinq composantes calculées · indicateur interne</div></div></div><div id="qualityScores">${empty('Chargement…')}</div></article><article class="card" style="margin-top:13px"><div class="card-head"><div><h2>Datasets Eurostat configurés</h2><div class="subtitle">Catalogue actif et dernière version importée</div></div></div><div id="eurostatDatasets">${empty('Chargement…')}</div></article>`;
    if (!$('#entityModal')) document.body.insertAdjacentHTML('beforeend','<div class="modal-backdrop" id="entityModal"><article class="modal"><div class="modal-head"><div id="modalTitle"></div><button class="modal-close" aria-label="Fermer">×</button></div><div id="modalBody"></div></article></div>');
    document.querySelectorAll('[data-open-view]').forEach(button => button.onclick = () => showView(button.dataset.openView));
    bindControls();
  }

  function renderDashboard() {
    const data = state.dashboard;
    const salary = data.salary?.primary ?? null;
    const tension = data.tension;
    const cards = [
      ['Métiers suivis',data.kpis.occupations,'Référentiel en base'],
      ['Compétences',data.kpis.skills,'Référentiel en base'],
      ['Offres · 12 mois',data.kpis.offers_12m,data.kpis.offers_latest_period?`jusqu'au ${formatDate(data.kpis.offers_latest_period)}`:'Aucune offre importée'],
      ['Pays',data.kpis.countries,'Calculés depuis les géographies'],
      ['Régions',data.kpis.regions,'Niveaux régionaux observés'],
      ['Salaire central',salary?formatMetric(salary.value,salary.unit):null,salary?`${formatNumber(salary.sample_size)} valeurs observées`:'Aucun salaire importé'],
      ['Tension',tension?formatMetric(tension.value,tension.unit):null,tension?`${tension.is_official?'Donnée source':'Calcul interne'} · ${formatNumber(tension.sample_size)} observations`:'Aucun indicateur importé'],
      ['Observations',data.kpis.observations,'Toutes sources'],
    ];
    $('#dashboardKpis').innerHTML = cards.map((card,index) => `<article class="card kpi" style="--accent:${['var(--lime)','var(--mint)','var(--coral)','var(--amber)'][index%4]}"><div class="kpi-top"><span>${card[0]}</span></div><div class="kpi-value">${typeof card[1]==='string'?escapeHtml(card[1]):formatNumber(card[1])}</div><span class="delta">${escapeHtml(card[2])}</span></article>`).join('');
    $('#dataStatus').innerHTML = '<i style="background:var(--mint)"></i>Base connectée';
    $('#dashboardTrends').innerHTML = data.top_skill_trends.length ? data.top_skill_trends.map((item,index) => `<div class="rank"><span class="rank-num">${String(index+1).padStart(2,'0')}</span><div class="rank-name"><b>${escapeHtml(item.name)}</b><small>Calcul interne · v${escapeHtml(item.method_version)}</small></div><div class="rank-score">${formatNumber(item.score)}<small>${item.growth >= 0 ? '+' : ''}${formatNumber(item.growth)} %</small></div></div>`).join('') : empty('Aucun TrendScore calculé.');
    renderSeries();
    const ranked = data.top_occupations_by_offers;
    const maximum = Math.max(...ranked.map(item => item.offers),1);
    $('#topOccupations').innerHTML = ranked.length ? ranked.map(item => `<div class="bar-row"><span>${escapeHtml(item.name)}</span><div class="bar-track"><div class="bar-fill" style="--w:${100*item.offers/maximum}%"></div></div><b>${formatNumber(item.offers)}</b></div>`).join('') : empty('Aucune offre France Travail rattachée à un métier.');
    $('#occupationTrends').innerHTML = data.top_occupation_trends.length ? data.top_occupation_trends.map((item,index)=>`<div class="rank"><span class="rank-num">${String(index+1).padStart(2,'0')}</span><div class="rank-name"><b>${escapeHtml(item.name)}</b><small>${formatDate(item.period_to||item.period)} · ${item.is_official?'observé':'calcul interne'}</small></div><div class="rank-score">${item.score == null ? formatNumber(item.volume) : formatNumber(item.score)}<small>${item.growth>=0?'+':''}${formatNumber(item.growth)} %</small></div></div>`).join('') : empty('Deux périodes d’offres sont nécessaires pour calculer une hausse.');
    $('#marketSnapshot').innerHTML = `<div class="fact"><span>Salaire central</span><b>${salary?formatMetric(salary.value,salary.unit):'Non disponible'}</b></div><div class="fact"><span>Couverture salaire</span><b>${salary?`${formatNumber(salary.sample_size)} valeurs · ${formatNumber(salary.occupation_count)} métiers`:'—'}</b></div><div class="fact"><span>Méthode salaire</span><b>${salary?escapeHtml(salary.method):'—'}</b></div><div class="fact"><span>Tension moyenne</span><b>${tension?formatMetric(tension.value,tension.unit):'Non disponible'}</b></div><div class="fact"><span>Statut tension</span><b>${tension?(tension.is_official?'Donnée source':'Calcul interne'):'—'}</b></div>`;
    $('#dashboardUpdates').innerHTML = data.source_updates.length ? data.source_updates.map(source=>`<div class="fact"><span>${escapeHtml(source.name)}</span><b>${formatDate(source.last_success_at)}</b></div>`).join('')+`<div class="fact"><span>Dernière observation chargée</span><b>${formatDate(data.latest_update)}</b></div>` : empty('Aucune source configurée.');
  }

  function renderSeries() {
    if (!state.series.length) { $('#marketChart').innerHTML = empty('Aucune série job_offers disponible.'); $('#seriesProvenance').textContent='France Travail · aucune donnée importée'; return; }
    const width=760,height=210,pad=28; const values=state.series.map(item=>item.value); const min=Math.min(...values),max=Math.max(...values); const span=max-min||1;
    const points=state.series.map((item,index)=>`${pad+index*(width-2*pad)/Math.max(1,state.series.length-1)},${height-pad-(item.value-min)*(height-2*pad)/span}`).join(' ');
    $('#marketChart').innerHTML=`<svg class="line-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"><polyline class="trend-line" points="${points}"/></svg>`;
    $('#seriesSubtitle').textContent=`${state.series.length} périodes observées`;
    $('#seriesProvenance').textContent='France Travail · somme des offres rattachées';
  }

  function occupationCard(item) {
    const offers=metricValue(item,'job_offers'), difficulty=metricValue(item,'recruitment_difficulty');
    return `<article class="catalog-card" data-occupation-id="${escapeHtml(item.id)}"><div class="top"><div><span class="tag">${escapeHtml(item.sector||item.isco_code||'Métier')}</span><h3 style="margin-top:11px">${escapeHtml(item.canonical_name)}</h3></div><span class="kpi-icon" style="--accent:var(--mint)">${iconBrief}</span></div><p>${escapeHtml(item.description||'Description ESCO non disponible.')}</p><div class="chips">${item.skills.map(skill=>`<span class="chip">${escapeHtml(skill.name)}</span>`).join('')||'<span class="chip">Compétences non importées</span>'}</div><div class="metric-row"><div><b>${formatNumber(offers)}</b>offres liées</div><div><b>${formatNumber(difficulty)}</b>difficulté</div><div><b>${escapeHtml(item.isco_code||'—')}</b>ISCO</div></div></article>`;
  }

  function renderOccupations(items=state.occupations) {
    $('#occupationCards').innerHTML=items.length?items.map(occupationCard).join(''):empty('Aucun métier ne correspond aux critères.');
    $('#occupationCount').innerHTML=`<i style="background:var(--mint)"></i>${formatNumber(items.length)} affichés`;
    document.querySelectorAll('[data-occupation-id]').forEach(card=>card.onclick=()=>openOccupation(card.dataset.occupationId));
  }

  function skillCard(item) {
    const trend=item.trend;
    return `<article class="catalog-card" data-skill-id="${escapeHtml(item.id)}"><div class="top"><div><span class="tag">${escapeHtml(item.skill_type||'Non classée')}</span><h3 style="margin-top:11px">${escapeHtml(item.canonical_name)}</h3></div><b style="font:800 22px 'Manrope';color:var(--lime)">${trend?formatNumber(trend.score):'—'}</b></div><p>${escapeHtml(item.description||'Description ESCO non disponible.')}</p><div class="metric-row"><div><b>${formatNumber(item.occupation_count)}</b>métiers liés</div><div><b class="${trend&&trend.growth>=0?'trend-up':''}">${trend?`${trend.growth>=0?'+':''}${formatNumber(trend.growth)} %`:'—'}</b>croissance</div><div><b>${trend?`v${escapeHtml(trend.method_version)}`:'—'}</b>méthode</div></div></article>`;
  }

  function renderSkills(items=state.skills) {
    $('#skillCards').innerHTML=items.length?items.map(skillCard).join(''):empty('Aucune compétence ne correspond aux critères.');
    $('#skillCount').innerHTML=`<i style="background:var(--mint)"></i>${formatNumber(items.length)} affichées`;
    document.querySelectorAll('[data-skill-id]').forEach(card=>card.onclick=()=>openSkill(card.dataset.skillId));
  }

  function renderTrends() {
    const data=state.future;if(!data?.items?.length){$('#trendQuadrant').innerHTML=empty(data?.warning||'Aucune édition prospective importée.');$('#futureComparison').innerHTML=empty('Importez une édition WEF structurée pour activer la comparaison.');return}
    const items=data.items.filter(item=>item.central_share!=null),changes=items.map(item=>item.projected_change),min=Math.min(...changes),max=Math.max(...changes),span=max-min||1;
    $('#futureEdition').innerHTML=data.editions.map(item=>`<option value="${escapeHtml(item.edition)}" ${item.edition===data.selected_edition?'selected':''}>${escapeHtml(item.edition)} · ${item.publication_year}</option>`).join('');
    $('#futureSubtitle').textContent=`X = part centrale (%) · Y = variation projetée (%) · horizon ${data.horizon_year||'non précisé'}`;$('#futureSource').textContent=`${data.report_title} · édition ${data.selected_edition}`;
    $('#trendQuadrant').innerHTML='<span class="quad-label ql1">Centrales et en progression</span><span class="quad-label ql2">Émergentes</span><span class="quad-label ql3">En retrait</span><span class="quad-label ql4">Stables</span>'+items.map((item,index)=>{const x=Math.max(7,Math.min(93,item.central_share));const y=8+84*(item.projected_change-min)/span;return `<button class="bubble" data-name="${escapeHtml(item.name)}" style="--x:${x}%;--y:${y}%;--s:34px;--c:${index%3===0?'var(--lime)':index%3===1?'var(--mint)':'var(--coral)'}" title="${escapeHtml(item.name)} · centralité ${formatNumber(item.central_share)} % · projection ${formatNumber(item.projected_change)} % · ${escapeHtml(item.figure_table)}"></button>`}).join('')+'<span class="axis-x">Part des employeurs considérant la compétence centrale (%) →</span><span class="axis-y">Progression projetée (%) →</span>';
    $('#futureComparison').innerHTML=profileTable(['Compétence','Projection','Observation','Périodes','Écart','Source'],data.items.map(item=>`<tr><td><b>${escapeHtml(item.name)}</b><small style="display:block;color:var(--muted)">${escapeHtml(item.category||'Non classée')} · ${escapeHtml(item.mapping_method||'non rapprochée')}</small></td><td>${item.projected_change>=0?'+':''}${formatNumber(item.projected_change)} %</td><td>${item.observed_growth==null?'—':`${item.observed_growth>=0?'+':''}${formatNumber(item.observed_growth)} %`}</td><td>horizon ${data.horizon_year||'—'}${item.observed_period?` · observé ${formatDate(item.observed_period)}`:''}</td><td>${item.difference==null?'—':`${item.difference>=0?'+':''}${formatNumber(item.difference)} pts`}</td><td>${escapeHtml(item.figure_table)}</td></tr>`),'Aucune projection importée.')+`<div class="notice" style="margin-top:14px">${escapeHtml(data.warning)}</div>`;
  }

  function renderCompareSelectors() {
    if(!state.occupations.length){$('#compareSelectors').innerHTML=empty('Aucun métier disponible.');return;}
    const defaults=state.occupations.slice(0,3); const options=state.occupations.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.canonical_name)}</option>`).join('');
    $('#compareSelectors').innerHTML=[0,1,2].map((index)=>`<div class="compare-person"><span class="tag">Métier ${String.fromCharCode(65+index)}</span><select class="job-select" data-compare-index="${index}">${options}</select></div>`).join('');
    document.querySelectorAll('.job-select').forEach((select,index)=>{if(defaults[index])select.value=defaults[index].id;select.onchange=renderComparison});
    renderComparison();
  }

  async function renderComparison() {
    const ids=[...document.querySelectorAll('.job-select')].map(select=>select.value).filter(Boolean);
    if(!ids.length)return;
    $('#compareResult').innerHTML=empty('Chargement de la comparaison…');
    try{
      const rows=await Promise.all(ids.map(id=>apiGet(`/api/v1/occupations/${encodeURIComponent(id)}`)));
      const value=(row,metric)=>{const items=row.market.filter(item=>item.metric===metric);return items.length?items.reduce((sum,item)=>sum+item.value,0):null};
      const common=rows.map(row=>new Set(row.skills.map(skill=>skill.name))).reduce((left,right)=>new Set([...left].filter(item=>right.has(item))));
      const body=[['Offres', 'job_offers'],['Demandeurs','job_seekers'],['Embauches','hires'],['Salaire moyen','salary_average'],['Difficulté de recrutement','recruitment_difficulty']].map(([label,metric])=>`<tr><td>${label}</td>${rows.map(row=>`<td><b>${formatNumber(value(row,metric))}</b></td>`).join('')}</tr>`).join('');
      $('#compareResult').innerHTML=`<table class="compare-table"><thead><tr><th>Indicateur</th>${rows.map(row=>`<th>${escapeHtml(row.canonical_name)}</th>`).join('')}</tr></thead><tbody>${body}<tr><td>Compétences communes</td><td colspan="${rows.length}">${[...common].map(item=>`<span class="chip">${escapeHtml(item)}</span>`).join(' ')||'<span class="empty-value">Aucune relation commune importée</span>'}</td></tr></tbody></table><div class="provenance"><span>Valeurs lues dans les observations rattachées aux métiers</span><span>— = donnée absente</span></div>`;
    }catch(error){$('#compareResult').innerHTML=errorState(`Comparaison indisponible : ${error.message}`)}
  }

  function renderGeographies() {
    const data=state.geographies;
    if(data?.metric) $('#geoMetric').value=data.metric;
    $('#geoPeriod').innerHTML=`<i style="background:var(--mint)"></i>${data?.period?formatDate(data.period):'Aucune période'}`;
    $('#geoCards').innerHTML=data?.items?.length?data.items.map(item=>`<article class="card"><span class="tag">${escapeHtml(item.code)}</span><h3 style="margin-top:12px">${escapeHtml(item.name)}</h3><div class="geo-value">${formatNumber(item.value)}</div><span class="subtitle">${escapeHtml(item.unit)} · ${escapeHtml(data.metric)}</span></article>`).join(''):empty('Aucun indicateur territorial pour cette métrique.');
  }

  function renderSources() {
    $('#sourceCount').innerHTML=`<i style="background:var(--mint)"></i>${state.sources.length} sources`;
    $('#sourceCards').innerHTML=state.sources.length?state.sources.map(source=>`<article class="card source-card"><div class="source-logo">${escapeHtml(source.name.split(' ').map(word=>word[0]).join('').slice(0,2))}</div><h2>${escapeHtml(source.name)}</h2><p class="subtitle">Type : ${escapeHtml(source.type)}${source.requires_credentials?' · OAuth requis':''}</p><div class="fact"><span>ConfidenceScore</span><b>${source.quality_score==null?'Non calculé':formatNumber(source.quality_score)+' / 100'}</b></div><div class="source-meta"><span class="dot" style="background:${source.last_success_at?'var(--mint)':'var(--amber)'}"></span>${source.last_success_at?'Dernier succès : '+formatDate(source.last_success_at):'Aucun import réussi enregistré'}</div></article>`).join(''):empty('Aucune source configurée.');
    $('#qualityScores').innerHTML=state.quality.length?`<div class="profile-table-wrap"><table class="data-table"><thead><tr><th>Source · métrique</th><th>Score</th><th>Qualité source</th><th>Récence</th><th>Couverture</th><th>Cohérence</th><th>Accord inter-sources</th><th>Échantillon</th></tr></thead><tbody>${state.quality.map(item=>`<tr><td><b>${escapeHtml(item.source_name)}</b><small style="display:block;color:var(--muted)">${escapeHtml(item.dataset||'source')} · ${escapeHtml(metricLabel(item.metric))}</small></td><td><b>${formatNumber(item.score)} / 100</b></td><td>${formatNumber(item.components.source_quality)}</td><td>${formatNumber(item.components.recency)}</td><td>${formatNumber(item.components.coverage)}</td><td>${formatNumber(item.components.consistency)}</td><td>${formatNumber(item.components.cross_source_agreement)}</td><td>${formatNumber(item.sample_size)}</td></tr>`).join('')}</tbody></table></div><div class="provenance"><span>Méthode ${escapeHtml(state.quality[0].method_version)}</span><span>Score interne · non officiel</span></div>`:empty('Aucun ConfidenceScore calculé. Lancez le pipeline qualité après un import.');
    $('#eurostatDatasets').innerHTML=state.eurostat.length?`<table class="data-table"><thead><tr><th>Profil</th><th>Dataset</th><th>Famille</th><th>Dernière version</th></tr></thead><tbody>${state.eurostat.map(item=>`<tr><td>${escapeHtml(item.name)}</td><td>${escapeHtml(item.code)}</td><td>${escapeHtml(item.family)}</td><td>${item.imported?formatDate(item.last_update):'Non importé'}</td></tr>`).join('')}</tbody></table>`:empty('Aucun profil Eurostat configuré.');
    const latest=state.sources.map(source=>source.last_success_at).filter(Boolean).sort().at(-1);
    $('#sourceStatus').innerHTML=`<b><span class="dot" style="background:${latest?'var(--mint)':'var(--amber)'}"></span>${latest?'Sources connectées':'Sources configurées'}</b>${latest?'Dernier import réussi<br>'+formatDate(latest):'Aucun import réel enregistré'}`;
  }

  function profileTable(headers,rows,emptyMessage) {
    return rows.length?`<div class="profile-table-wrap"><table class="data-table"><thead><tr>${headers.map(item=>`<th>${escapeHtml(item)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`:empty(emptyMessage);
  }

  function renderOccupationTimeline(profile,key) {
    const target=$('#occupationTimelineChart');
    if(!target)return;
    const [metric,unit]=String(key||'').split('|');
    const points=profile.timeline.filter(item=>item.metric===metric&&item.unit===unit).sort((a,b)=>String(a.period).localeCompare(String(b.period)));
    if(!points.length){target.innerHTML=empty('Aucune série temporelle disponible.');return}
    const width=900,height=210,pad=34,values=points.map(item=>item.value),min=Math.min(...values),max=Math.max(...values),span=max-min||1;
    const coordinates=points.map((item,index)=>({x:pad+index*(width-2*pad)/Math.max(1,points.length-1),y:height-pad-(item.value-min)*(height-2*pad)/span,item}));
    target.innerHTML=`<svg class="line-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"><line x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}" stroke="var(--line)"/><polyline class="trend-line" points="${coordinates.map(point=>`${point.x},${point.y}`).join(' ')}"/>${coordinates.map(point=>`<circle class="point" cx="${point.x}" cy="${point.y}" r="4"><title>${escapeHtml(formatDate(point.item.period))} · ${escapeHtml(formatMetric(point.item.value,unit))}</title></circle>`).join('')}</svg><div class="provenance"><span>${formatDate(points[0].period)} → ${formatDate(points.at(-1).period)}</span><span>${points.length} période${points.length>1?'s':''} · ${escapeHtml(points[0].aggregation)}</span></div>`;
  }

  function renderOccupationProfile(row) {
    currentOccupation=row;
    const aliases=flattenLocalized(row.aliases),labels=flattenLocalized(row.multilingual_labels);
    const marketRows=row.market_summary.map(item=>`<tr><td><b>${escapeHtml(metricLabel(item.metric))}</b><small style="display:block;color:var(--muted)">${escapeHtml(item.metric)}</small></td><td>${formatMetric(item.value,item.unit)}</td><td>${escapeHtml(item.aggregation)}</td><td>${formatDate(item.period_from)} → ${formatDate(item.period_to)}</td><td>${item.is_official?'Source officielle':'Calcul interne'}</td></tr>`);
    const geographyRows=row.geographies.map(item=>`<tr><td><b>${escapeHtml(item.geography_name)}</b><small style="display:block;color:var(--muted)">${escapeHtml(item.geography_code)} · ${escapeHtml(item.geography_level)}</small></td><td>${escapeHtml(metricLabel(item.metric))}</td><td>${formatMetric(item.value,item.unit)}</td><td>${formatDate(item.period)}</td></tr>`);
    const sourceRows=row.sources.map(item=>`<tr><td><b>${escapeHtml(item.source_name)}</b><small style="display:block;color:var(--muted)">${escapeHtml(item.kind==='reference'?'Référentiel':'Observations')}</small></td><td>${escapeHtml(item.dataset_name||item.dataset_code||'Référentiel principal')}</td><td>${item.observation_count||0} observation${item.observation_count===1?'':'s'}${item.relationship_count?` · ${item.relationship_count} relation${item.relationship_count===1?'':'s'}`:''}</td><td>${item.period_from?`${formatDate(item.period_from)} → ${formatDate(item.period_to)}`:'—'}</td><td>${formatDate(item.last_imported_at)}</td></tr>`);
    const timelineKeys=[...new Map(row.timeline.map(item=>[`${item.metric}|${item.unit}`,item])).entries()];
    const timelineOptions=timelineKeys.map(([key,item])=>`<option value="${escapeHtml(key)}">${escapeHtml(metricLabel(item.metric))} · ${escapeHtml(item.unit)}</option>`).join('');
    const mappings=(row.external_mappings||[]).map(item=>`<div class="fact"><span>${escapeHtml(item.system)} · ${escapeHtml(item.relation)}</span><b>${escapeHtml(item.code)}${item.label?` — ${escapeHtml(item.label)}`:''}</b></div>`).join('');
    $('#occupation-detail').innerHTML=`
      <button class="secondary profile-back" data-profile-back>← Retour aux métiers</button>
      <header class="profile-hero"><div class="profile-hero-top"><div><div class="eyebrow">Fiche métier dynamique</div><h1>${escapeHtml(row.canonical_name)}</h1><p>${escapeHtml(row.description||'Description non disponible dans le référentiel importé.')}</p></div><div class="profile-meta"><span class="tag">${escapeHtml(row.sector||'Secteur non renseigné')}</span><span class="tag">ISCO ${escapeHtml(row.isco_code||'—')}</span></div></div></header>
      <nav class="profile-tabs" aria-label="Sections de la fiche"><button data-profile-section="profile-information">Informations</button><button data-profile-section="profile-skills">Compétences</button><button data-profile-section="profile-market">Marché</button><button data-profile-section="profile-geography">Géographie</button><button data-profile-section="profile-timeline">Temporalité</button><button data-profile-section="profile-sources">Sources</button></nav>
      <article class="card profile-section" id="profile-information"><div class="card-head"><div><div class="eyebrow">01 · Informations</div><h2>Référentiels et identifiants</h2></div></div><div class="profile-grid"><div><div class="fact"><span>Secteur</span><b>${escapeHtml(row.sector||'—')}</b></div><div class="fact"><span>Code ISCO</span><b>${escapeHtml(row.isco_code||'—')}</b></div><div class="fact"><span>URI ESCO</span><b class="profile-code">${escapeHtml(row.esco_uri||'—')}</b></div><div class="fact"><span>Dernière mise à jour</span><b>${formatDate(row.updated_at)}</b></div>${mappings}</div><div><h3>Alias et libellés multilingues</h3><div class="chips" style="margin-top:12px">${[...aliases,...labels].map(item=>`<span class="chip">${escapeHtml(item.language)} · ${escapeHtml(item.term)}</span>`).join('')||'<span class="empty-value">Aucun alias importé</span>'}</div></div></div></article>
      <article class="card profile-section" id="profile-skills"><div class="card-head"><div><div class="eyebrow">02 · Compétences</div><h2>${row.skills.length} compétence${row.skills.length===1?'':'s'} reliée${row.skills.length===1?'':'s'}</h2></div><span class="subtitle">Relations essentielles et optionnelles</span></div><div class="profile-skill-grid">${row.skills.map(skill=>`<div class="profile-skill ${escapeHtml(skill.relationship)}"><span class="tag">${escapeHtml(relationshipLabel(skill.relationship))}</span><h3 style="margin-top:10px">${escapeHtml(skill.name)}</h3><p>${escapeHtml(skill.description||'Description non disponible.')}</p><div class="profile-meta"><span class="chip">${escapeHtml(skill.skill_type||'Type inconnu')}</span>${skill.source?`<span class="chip">${escapeHtml(skill.source)}</span>`:''}${skill.confidence!=null?`<span class="chip">Confiance ${formatNumber(skill.confidence)}</span>`:''}</div></div>`).join('')||empty('Aucune relation métier–compétence importée.')}</div></article>
      <article class="card profile-section" id="profile-market"><div class="card-head"><div><div class="eyebrow">03 · Marché</div><h2>Indicateurs disponibles</h2></div><span class="subtitle">Les unités source ne sont pas converties</span></div><div class="profile-stat-grid">${row.market_summary.slice(0,6).map(item=>`<div class="profile-stat"><small>${escapeHtml(metricLabel(item.metric))}</small><b>${formatMetric(item.value,item.unit)}</b><small>${item.observation_count} observation${item.observation_count===1?'':'s'} · ${escapeHtml(item.aggregation)}</small></div>`).join('')||empty('Aucun indicateur de marché rattaché.')}</div>${profileTable(['Indicateur','Valeur','Agrégation','Période','Statut'],marketRows,'Aucun indicateur de marché rattaché.')}</article>
      <article class="card profile-section" id="profile-geography"><div class="card-head"><div><div class="eyebrow">04 · Géographie</div><h2>Dernières valeurs par territoire</h2></div></div>${profileTable(['Territoire','Indicateur','Valeur','Période'],geographyRows,'Aucune ventilation géographique disponible.')}</article>
      <article class="card profile-section" id="profile-timeline"><div class="card-head"><div><div class="eyebrow">05 · Temporalité</div><h2>Évolution observée</h2></div>${timelineKeys.length?`<select class="filter" id="occupationTimelineMetric">${timelineOptions}</select>`:''}</div><div class="profile-chart" id="occupationTimelineChart">${empty('Aucune série temporelle disponible.')}</div></article>
      <article class="card profile-section" id="profile-sources"><div class="card-head"><div><div class="eyebrow">06 · Sources</div><h2>Provenance et fraîcheur</h2></div><span class="subtitle">Traçabilité des observations et relations</span></div>${profileTable(['Source','Dataset','Couverture','Période','Import'],sourceRows,'Aucune provenance enregistrée.')}<details class="profile-raw" style="margin-top:18px"><summary>Voir les ${row.market.length} observations brutes</summary>${profileTable(['Métrique','Valeur','Territoire','Période','Source'],row.market.map(item=>`<tr><td>${escapeHtml(item.metric)}</td><td>${formatMetric(item.value,item.unit)}</td><td>${escapeHtml(item.geography_name)} (${escapeHtml(item.geography_code)})</td><td>${formatDate(item.period)}</td><td>${escapeHtml(item.source||'—')}${item.dataset?` · ${escapeHtml(item.dataset)}`:''}</td></tr>`),'Aucune observation brute.')}</details></article>`;
    $('[data-profile-back]').onclick=closeOccupationProfile;
    document.querySelectorAll('[data-profile-section]').forEach(button=>button.onclick=()=>document.getElementById(button.dataset.profileSection)?.scrollIntoView({behavior:'smooth'}));
    const selector=$('#occupationTimelineMetric');if(selector){selector.onchange=()=>renderOccupationTimeline(row,selector.value);renderOccupationTimeline(row,selector.value)}
  }

  async function openOccupation(id,{push=true}={}) {
    const active=document.querySelector('.view.active')?.id;
    if(active&&!['occupation-detail','skill-detail'].includes(active))occupationReturnView=active;
    $('#occupation-detail').innerHTML=empty('Lecture de la fiche métier…');showView('occupation-detail');
    if(push&&location.hash!==`#occupation/${encodeURIComponent(id)}`)history.pushState({occupation:id},'',`#occupation/${encodeURIComponent(id)}`);
    try{renderOccupationProfile(await apiGet(`/api/v1/occupations/${encodeURIComponent(id)}`))}catch(error){$('#occupation-detail').innerHTML=`<button class="secondary profile-back" data-profile-back>← Retour</button>${errorState(`Fiche indisponible : ${error.message}`)}`;$('[data-profile-back]').onclick=closeOccupationProfile}
  }

  function closeOccupationProfile(){
    currentOccupation=null;
    if(location.hash.startsWith('#occupation/')&&history.state?.occupation){history.back();return}
    history.replaceState(null,'',location.pathname+location.search);showView(occupationReturnView);
  }

  function renderSkillProfile(row) {
    const aliases=[...flattenLocalized(row.aliases),...flattenLocalized(row.multilingual_labels)];
    const trendComponents=row.trend?.components?Object.entries(row.trend.components).map(([name,value])=>`<div class="profile-stat"><small>${escapeHtml(metricLabel(name))}</small><b>${formatNumber(value)} / 100</b><small>composante normalisée</small></div>`).join(''):'';
    const marketRows=row.market_summary.map(item=>`<tr><td><b>${escapeHtml(metricLabel(item.metric))}</b></td><td>${formatMetric(item.value,item.unit)}</td><td>${escapeHtml(item.aggregation)}</td><td>${formatDate(item.period_from)} → ${formatDate(item.period_to)}</td><td>${item.is_official?'Source officielle':'Calcul interne'}</td></tr>`);
    const occupationRows=row.occupations.map(item=>`<tr><td><button class="link-btn" data-related-occupation="${escapeHtml(item.id)}">${escapeHtml(item.name)}</button></td><td>${escapeHtml(item.sector||'—')}</td><td>${escapeHtml(relationshipLabel(item.relationship))}</td><td>${formatMetric(item.offers,'offer')}</td><td>${item.salary==null?'—':formatMetric(item.salary,'EUR/year')}</td><td>${item.tension==null?'—':formatNumber(item.tension)}</td></tr>`);
    const regionRows=row.regions.map(item=>`<tr><td>${escapeHtml(item.name)}<small style="display:block;color:var(--muted)">${escapeHtml(item.code)} · ${escapeHtml(item.level)}</small></td><td>${escapeHtml(metricLabel(item.metric))}</td><td>${formatMetric(item.value,item.unit)}</td><td>${formatDate(item.period)}</td></tr>`);
    $('#skill-detail').innerHTML=`
      <button class="secondary profile-back" data-skill-back>← Retour aux compétences</button>
      <header class="profile-hero"><div class="profile-hero-top"><div><div class="eyebrow">Fiche compétence dynamique</div><h1>${escapeHtml(row.canonical_name)}</h1><p>${escapeHtml(row.description||'Description non disponible dans le référentiel importé.')}</p></div><div class="profile-meta"><span class="tag">${escapeHtml(row.skill_type||'Type non renseigné')}</span><span class="tag">${row.occupations.length} métier${row.occupations.length===1?'':'s'}</span></div></div></header>
      <nav class="profile-tabs" aria-label="Sections de la fiche"><button data-profile-section="skill-information">Informations</button><button data-profile-section="skill-trend">Tendance</button><button data-profile-section="skill-occupations">Métiers</button><button data-profile-section="skill-sectors">Secteurs</button><button data-profile-section="skill-regions">Régions</button><button data-profile-section="skill-market">Marché</button><button data-profile-section="skill-neighbors">Compétences voisines</button><button data-profile-section="skill-sources">Sources</button></nav>
      <article class="card profile-section" id="skill-information"><div class="eyebrow">01 · Informations</div><h2>Référentiel ESCO</h2><div class="fact"><span>Type</span><b>${escapeHtml(row.skill_type||'—')}</b></div><div class="fact"><span>URI ESCO</span><b class="profile-code">${escapeHtml(row.esco_uri||'—')}</b></div><div class="fact"><span>Mise à jour</span><b>${formatDate(row.updated_at)}</b></div><div class="chips" style="margin-top:14px">${aliases.map(item=>`<span class="chip">${escapeHtml(item.language)} · ${escapeHtml(item.term)}</span>`).join('')||'<span class="empty-value">Aucun alias importé</span>'}</div></article>
      <article class="card profile-section" id="skill-trend"><div class="card-head"><div><div class="eyebrow">02 · Tendance</div><h2>TrendScore interne</h2></div><span class="subtitle">Calcul distinct des données officielles</span></div><div class="profile-stat-grid">${row.trend?`<div class="profile-stat"><small>Score</small><b>${formatNumber(row.trend.score)} / 100</b><small>méthode v${escapeHtml(row.trend.method_version)}</small></div><div class="profile-stat"><small>Croissance brute</small><b>${row.trend.growth>=0?'+':''}${formatNumber(row.trend.growth)} %</b><small>dernière période calculée</small></div><div class="profile-stat"><small>Historique</small><b>${row.trends.length}</b><small>période${row.trends.length===1?'':'s'} calculée${row.trends.length===1?'':'s'}</small></div>${trendComponents}`:empty('Aucun TrendScore calculé.')}</div>${row.trend?.calculation?`<div class="notice" style="margin-top:14px">Signal : ${escapeHtml(row.trend.calculation.signal)} · ${formatNumber(row.trend.calculation.observation_count)} observation(s) · ${formatNumber(row.trend.calculation.geography_count)} territoire(s) · ${formatNumber(row.trend.calculation.source_count)} source(s).</div>`:''}${profileTable(['Période','Score','Croissance','Méthode'],row.trends.map(item=>`<tr><td>${formatDate(item.period)}</td><td>${formatNumber(item.score)} / 100</td><td>${item.growth>=0?'+':''}${formatNumber(item.growth)} %</td><td>v${escapeHtml(item.method_version)} · interne</td></tr>`),'Aucun historique de tendance.')}</article>
      <article class="card profile-section" id="skill-occupations"><div class="eyebrow">03 · Métiers</div><h2>Métiers associés</h2>${profileTable(['Métier','Secteur','Relation','Offres','Salaire','Tension'],occupationRows,'Aucun métier associé.')}</article>
      <article class="card profile-section" id="skill-sectors"><div class="eyebrow">04 · Secteurs</div><h2>Diffusion sectorielle</h2><div class="profile-stat-grid" style="margin-top:14px">${row.sectors.map(item=>`<div class="profile-stat"><small>${escapeHtml(item.name)}</small><b>${item.occupation_count} métier${item.occupation_count===1?'':'s'}</b><small>${formatMetric(item.offers,'offer')} rattachées</small></div>`).join('')||empty('Aucun secteur déduit des métiers liés.')}</div></article>
      <article class="card profile-section" id="skill-regions"><div class="eyebrow">05 · Régions</div><h2>Dernières valeurs territoriales</h2>${profileTable(['Région','Indicateur','Valeur','Période'],regionRows,'Aucune donnée régionale rattachée aux métiers associés.')}</article>
      <article class="card profile-section" id="skill-market"><div class="eyebrow">06 · Offres, salaires et tension</div><h2>Indicateurs de marché</h2><div class="profile-stat-grid" style="margin-top:14px">${row.market_summary.slice(0,6).map(item=>`<div class="profile-stat"><small>${escapeHtml(metricLabel(item.metric))}</small><b>${formatMetric(item.value,item.unit)}</b><small>${item.observation_count} observation${item.observation_count===1?'':'s'}</small></div>`).join('')||empty('Aucun indicateur rattaché.')}</div>${profileTable(['Indicateur','Valeur','Agrégation','Période','Statut'],marketRows,'Aucun indicateur rattaché.')}</article>
      <article class="card profile-section" id="skill-neighbors"><div class="eyebrow">07 · Compétences voisines</div><h2>Cooccurrences dans les métiers</h2><div class="profile-skill-grid" style="margin-top:14px">${row.neighbors.map(item=>`<button class="profile-skill" style="color:var(--text);text-align:left" data-related-skill="${escapeHtml(item.id)}"><span class="tag">${escapeHtml(item.skill_type||'Compétence')}</span><h3 style="margin-top:10px">${escapeHtml(item.name)}</h3><p>${item.shared_occupation_count} métier${item.shared_occupation_count===1?' partagé':'s partagés'}</p></button>`).join('')||empty('Aucune compétence voisine déduite.')}</div></article>
      <article class="card profile-section" id="skill-sources"><div class="eyebrow">08 · Sources</div><h2>Provenance</h2>${profileTable(['Source','Observations','Relations','Métriques'],row.sources.map(item=>`<tr><td>${escapeHtml(item.source_name)}</td><td>${item.observation_count}</td><td>${item.relationship_count}</td><td>${item.metrics.map(metric=>escapeHtml(metricLabel(metric))).join(', ')||'Référentiel'}</td></tr>`),'Aucune provenance enregistrée.')}</article>`;
    $('[data-skill-back]').onclick=closeSkillProfile;
    document.querySelectorAll('[data-profile-section]').forEach(button=>button.onclick=()=>document.getElementById(button.dataset.profileSection)?.scrollIntoView({behavior:'smooth'}));
    document.querySelectorAll('[data-related-occupation]').forEach(button=>button.onclick=()=>openOccupation(button.dataset.relatedOccupation));
    document.querySelectorAll('[data-related-skill]').forEach(button=>button.onclick=()=>openSkill(button.dataset.relatedSkill));
  }

  async function openSkill(id,{push=true}={}) {
    const active=document.querySelector('.view.active')?.id;if(active&&!['occupation-detail','skill-detail'].includes(active))skillReturnView=active;
    $('#skill-detail').innerHTML=empty('Lecture de la fiche compétence…');showView('skill-detail');
    if(push&&location.hash!==`#skill/${encodeURIComponent(id)}`)history.pushState({skill:id},'',`#skill/${encodeURIComponent(id)}`);
    try{renderSkillProfile(await apiGet(`/api/v1/skills/${encodeURIComponent(id)}`))}catch(error){$('#skill-detail').innerHTML=`<button class="secondary profile-back" data-skill-back>← Retour</button>${errorState(`Fiche indisponible : ${error.message}`)}`;$('[data-skill-back]').onclick=closeSkillProfile}
  }

  function closeSkillProfile(){
    if(location.hash.startsWith('#skill/')&&history.state?.skill){history.back();return}
    history.replaceState(null,'',location.pathname+location.search);showView(skillReturnView);
  }

  function openModal(title,body){$('#modalTitle').innerHTML=`<h2>${title}</h2>`;$('#modalBody').innerHTML=body;$('#entityModal').classList.add('open')}

  function bindControls() {
    let occupationTimer, skillTimer, globalTimer;
    $('#occupationSearch').oninput=event=>{clearTimeout(occupationTimer);occupationTimer=setTimeout(()=>loadOccupations(event.target.value,$('#sectorFilter').value),250)};
    $('#sectorFilter').onchange=event=>loadOccupations($('#occupationSearch').value,event.target.value);
    $('#skillSearch').oninput=event=>{clearTimeout(skillTimer);skillTimer=setTimeout(()=>loadSkills(event.target.value,$('#skillTypeFilter').value),250)};
    $('#skillTypeFilter').onchange=event=>loadSkills($('#skillSearch').value,event.target.value);
    $('#geoMetric').onchange=event=>loadGeographies(event.target.value);
    $('#futureEdition').onchange=async event=>{state.future=await apiGet(`/api/v1/future-of-jobs?edition=${encodeURIComponent(event.target.value)}`);renderTrends()};
    $('#entityModal').onclick=event=>{if(event.target.id==='entityModal'||event.target.closest('.modal-close'))$('#entityModal').classList.remove('open')};
    $('#download').onclick=downloadCSV; $('#quadExport').onclick=downloadFutureCSV;
    const global=$('#globalSearch'),results=$('#searchResults');
    const selected={entity_type:'',language:'',source:''};
    const options=(values,current,allLabel)=>`<option value="">${allLabel}</option>`+values.map(value=>`<option value="${escapeHtml(value)}" ${value===current?'selected':''}>${escapeHtml(value)}</option>`).join('');
    const runGlobalSearch=async()=>{
      const query=global.value.trim();if(!query){results.classList.remove('show');return}
      const params=new URLSearchParams({q:query,limit:'8'});Object.entries(selected).forEach(([key,value])=>{if(value)params.set(key,value)});
      try{
        const rows=await apiGet(`/api/v1/search/suggestions?${params}`);
        const filters=`<div class="search-filter-row"><select aria-label="Type de résultat" data-search-filter="entity_type"><option value="">Métiers + compétences</option><option value="occupation" ${selected.entity_type==='occupation'?'selected':''}>Métiers</option><option value="skill" ${selected.entity_type==='skill'?'selected':''}>Compétences</option></select><select aria-label="Langue" data-search-filter="language">${options(state.searchFilters.languages||[],selected.language,'Toutes les langues')}</select><select aria-label="Source" data-search-filter="source">${options(state.searchFilters.sources||[],selected.source,'Toutes les sources')}</select></div>`;
        const items=rows.length?rows.map(item=>`<button class="search-item" style="width:100%;border:0;background:transparent;color:var(--text)" data-search-id="${escapeHtml(item.id)}" data-search-type="${escapeHtml(item.type)}"><span><b>${escapeHtml(item.name)}</b><small>${item.matched_term!==item.name?`via « ${escapeHtml(item.matched_term)} » · `:''}${escapeHtml(item.matched_source)}${item.matched_language?` · ${escapeHtml(item.matched_language)}`:''}</small></span><span><span class="tag">${item.type==='occupation'?'Métier':'Compétence'}</span><small class="search-score">${Math.round(item.score*100)} %</small></span></button>`).join(''):'<div class="search-item"><span>Aucun résultat, même avec la tolérance aux fautes.</span></div>';
        results.innerHTML=filters+items;results.classList.add('show');
        results.querySelectorAll('[data-search-filter]').forEach(select=>select.onchange=()=>{selected[select.dataset.searchFilter]=select.value;runGlobalSearch()});
        results.querySelectorAll('[data-search-id]').forEach(button=>button.onclick=()=>{results.classList.remove('show');global.value='';button.dataset.searchType==='occupation'?openOccupation(button.dataset.searchId):openSkill(button.dataset.searchId)});
      }catch(error){results.innerHTML='<div class="search-item">Recherche indisponible</div>';results.classList.add('show')}
    };
    global.oninput=()=>{clearTimeout(globalTimer);globalTimer=setTimeout(runGlobalSearch,180)};
    document.addEventListener('click',event=>{if(!event.target.closest('.search'))results.classList.remove('show')});
    document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{
      currentOccupation=null;
      if(location.hash.startsWith('#occupation/')||location.hash.startsWith('#skill/'))history.replaceState(null,'',location.pathname+location.search);
    }));
  }

  async function loadOccupations(query='',sector='') {
    $('#occupationCards').innerHTML=empty('Chargement…');
    try{const params=new URLSearchParams({limit:'60'});if(query)params.set('q',query);if(sector)params.set('sector',sector);state.occupations=await apiGet(`/api/v1/catalog/occupations?${params}`);occupations=state.occupations;renderOccupations();if(!query&&!sector)populateSectors();}catch(error){$('#occupationCards').innerHTML=errorState(`Métiers indisponibles : ${error.message}`)}
  }

  async function loadSkills(query='',type='') {
    $('#skillCards').innerHTML=empty('Chargement…');
    try{const params=new URLSearchParams({limit:'60'});if(query)params.set('q',query);if(type)params.set('skill_type',type);state.skills=await apiGet(`/api/v1/catalog/skills?${params}`);skills=state.skills;renderSkills();}catch(error){$('#skillCards').innerHTML=errorState(`Compétences indisponibles : ${error.message}`)}
  }

  function populateSectors(){const select=$('#sectorFilter');const current=select.value;const sectors=[...new Set(state.occupations.map(item=>item.sector).filter(Boolean))].sort();select.innerHTML='<option value="">Tous les secteurs</option>'+sectors.map(item=>`<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join('');select.value=current}
  async function loadGeographies(metric='job_offers'){try{state.geographies=await apiGet(`/api/v1/market/geographies?metric=${encodeURIComponent(metric)}&limit=60`);renderGeographies()}catch(error){$('#geoCards').innerHTML=errorState(`Territoires indisponibles : ${error.message}`)}}

  function downloadCSV(){const rows=[['type','nom','identifiant','volume_offres','score_tendance'],...state.occupations.map(item=>['metier',item.canonical_name,item.id,metricValue(item,'job_offers')??'', '']),...state.skills.map(item=>['competence',item.canonical_name,item.id,'',item.trend?.score??''])];const csv=rows.map(row=>row.map(value=>`"${String(value).replaceAll('"','""')}"`).join(';')).join('\n');const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='skillor-donnees-api.csv';link.click();URL.revokeObjectURL(link.href)}
  function downloadFutureCSV(){const data=state.future;if(!data?.items?.length)return;const rows=[['edition','rapport','horizon','competence','libelle_source','categorie','centralite','projection','croissance_observee','periode_observee','ecart','figure_table','geographie','secteur'],...data.items.map(item=>[data.selected_edition,data.report_title,data.horizon_year??'',item.name,item.source_label,item.category||'',item.central_share??'',item.projected_change,item.observed_growth??'',item.observed_period||'',item.difference??'',item.figure_table,item.geography,item.sector||''])];const csv=rows.map(row=>row.map(value=>`"${String(value).replaceAll('"','""')}"`).join(';')).join('\n');const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`future-of-jobs-${data.selected_edition}.csv`;link.click();URL.revokeObjectURL(link.href)}

  async function init() {
    hydrateShell();
    const initialRoute=location.hash.match(/^#occupation\/(.+)$/);
    if(initialRoute)openOccupation(decodeURIComponent(initialRoute[1]),{push:false});
    const initialSkillRoute=location.hash.match(/^#skill\/(.+)$/);
    if(initialSkillRoute)openSkill(decodeURIComponent(initialSkillRoute[1]),{push:false});
    const badge=$('#apiStatus');
    try{
      const [dashboardData,occupationData,skillData,trendsData,sourcesData,seriesData,geographyData,eurostatData,searchFilterData,qualityData,futureData]=await Promise.all([
        apiGet('/api/v1/dashboard'),apiGet('/api/v1/catalog/occupations?limit=60'),apiGet('/api/v1/catalog/skills?limit=60'),
        apiGet('/api/v1/trends/skills?limit=30'),apiGet('/api/v1/sources'),apiGet('/api/v1/market/series?metric=job_offers'),
        apiGet('/api/v1/market/geographies?metric=job_offers&limit=60'),apiGet('/api/v1/eurostat/datasets'),apiGet('/api/v1/search/filters'),apiGet('/api/v1/quality/scores?limit=100'),apiGet('/api/v1/future-of-jobs')]);
      Object.assign(state,{dashboard:dashboardData,occupations:occupationData,skills:skillData,trends:trendsData,future:futureData,sources:sourcesData,quality:qualityData,series:seriesData,geographies:geographyData,eurostat:eurostatData,searchFilters:searchFilterData});
      occupations=occupationData;skills=skillData;
      badge.innerHTML='<i style="background:var(--mint)"></i>API connectée';
      renderOccupations();renderSkills();renderTrends();renderCompareSelectors();renderGeographies();renderSources();populateSectors();renderDashboard();
    } catch(error) {
      badge.innerHTML='<i style="background:var(--coral)"></i>API indisponible';badge.title=error.message;
      ['dashboardKpis','occupationCards','skillCards','trendQuadrant','compareResult','geoCards','sourceCards'].forEach(id=>{const node=$('#'+id);if(node)node.innerHTML=errorState(`Impossible de charger l'API : ${error.message}`)});
      $('#dataStatus').innerHTML='<i style="background:var(--coral)"></i>Aucune donnée affichée';
    }
  }
  window.addEventListener('popstate',()=>{
    const route=location.hash.match(/^#occupation\/(.+)$/);
    if(route)openOccupation(decodeURIComponent(route[1]),{push:false});
    else if(location.hash.match(/^#skill\/(.+)$/))openSkill(decodeURIComponent(location.hash.match(/^#skill\/(.+)$/)[1]),{push:false});
    else if(document.querySelector('.view.active')?.id==='occupation-detail')showView(occupationReturnView);
    else if(document.querySelector('.view.active')?.id==='skill-detail')showView(skillReturnView);
  });
  init();
})();
