'use strict';
let token = location.hash.slice(1), inputs = [], env = null, logTask = null, logOffset = 0;
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path, options = {}) {
  const response = await fetch('/api/' + path, {...options, headers: {'X-Session-Token': token, ...(options.body instanceof Blob ? {} : {'Content-Type':'application/json'}), ...options.headers}});
  const value = await response.json();
  if (!response.ok) throw new Error(value.detail || 'Request failed');
  return value;
}
function message(text) { $('message').textContent = t(text); $('message').style.display = 'block'; }
function action(fn) { return async (...args) => { try { await fn(...args); } catch (error) { message(error.message); } }; }
function renderInputs() {
  $('inputs').innerHTML = inputs.map(x => `<li><span>${esc(x.name)}</span><button data-remove="${x.id}" aria-label="${esc(t('Remove '))}${esc(x.name)}">×</button></li>`).join('');
}
async function upload(files) {
  $('start').disabled = true;
  try {
    for (const file of files) {
      const key = 'nx-upload:' + [file.name, file.size, file.lastModified].join(':');
      let state;
      const saved = localStorage.getItem(key);
      if (saved) { try { state = await api('uploads/' + saved); } catch (_) {} }
      if (!state) state = await api('uploads', {method:'POST', body:JSON.stringify({name:file.name,size:file.size})});
      localStorage.setItem(key, state.id);
      $('upload-progress').hidden = false;
      while (state.offset < file.size) {
        const chunk = file.slice(state.offset, state.offset + 4 * 1024 * 1024);
        let result;
        for (let attempt = 0; attempt < 3; attempt++) {
          try { result = await api(`uploads/${state.id}?offset=${state.offset}`, {method:'PUT',body:chunk}); break; }
          catch (error) {
            const current = await api('uploads/' + state.id);
            if (current.offset > state.offset) { result = current; break; }
            if (attempt === 2) throw error;
          }
        }
        state.offset = result.offset;
        $('upload-progress').value = 100 * state.offset / file.size;
      }
      localStorage.removeItem(key);
      if (!inputs.some(x => x.id === state.id)) inputs.push({id:state.id,name:file.name});
      renderInputs();
    }
  } finally { $('start').disabled = false; $('upload-progress').hidden = true; }
}
function capability() {
  const profile = env?.profiles.find(p => p.id === $('game').value);
  $('build-options').hidden = $('kind').value !== 'build';
  $('mac').disabled = env?.system !== 'Darwin';
  if ($('mac').disabled) $('mac').checked = false;
  $('capability').textContent = t(profile?.reason || (profile?.graphics === 'vulkan' ? 'Vulkan game: MetalFX spatial upscaling is unavailable.' : 'Exact registered game versions are required for application builds.'));
  $('spatial').disabled = profile?.graphics === 'vulkan';
  if ($('spatial').disabled) $('spatial').value = '0';
  const ios = $('ios').checked, building = $('kind').value === 'build';
  $('separate-romfs').disabled = !building || !ios;
  if ($('separate-romfs').disabled) $('separate-romfs').checked = false;
  $('separate-romfs-hint').hidden = !building || !ios;
}
async function loadEnvironment() {
  env = await api('environment');
  $('host').textContent = `${env.system} / ${env.machine} · ${env.checks.filter(x => !x.available).length} ${t('missing dependencies')}`;
  const selected = $('game').value;
  $('game').innerHTML = '<option value="">Detect from input</option>' + env.profiles.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
  $('game').value = selected;
  $('checks').innerHTML = env.checks.map(c => `<div class="check ${c.available?'':'missing'}" title="${esc(c.path)}"><div class="check-heading"><strong>${c.available?'✓':'!'} ${esc(t(c.label || c.name))}</strong><a href="${esc(c.help_url)}" target="_blank" rel="noopener noreferrer">${esc(t(c.name==='sdk'?'SDK source':c.available?'Official instructions':'Get / install'))} ↗</a></div>${!c.available && c.auto_install?`<button data-install="${esc(c.name)}">${esc(t('Install'))}</button>`:''}${!c.available && !c.auto_install?`<span>${esc(t('Manual setup'))}</span>`:''}${c.install_method==='repository'?`<small>${esc(t('Third-party SDK: xybp888/iOS-SDKs, SHA-256 verified'))}</small>`:''}${c.install_method==='portable'?`<small>${esc(t('Verified portable tools; no administrator access required'))}</small>`:''}${c.install_method==='import'?`<small>${esc(t('Extracts your downloaded SDK archive locally'))}</small>`:''}${c.install_method==='direct'?`<small>${esc(t('Official download / local build; no Homebrew required'))}</small>`:''}${c.install_method==='xcode'?`<small>${esc(t('Installs through selected Xcode'))}</small>`:''}${c.install_method==='homebrew'?`<small>${esc(t('Installs through Homebrew'))}</small>`:''}${c.available && c.name !== 'dotnet'?'':`<p>${esc(t(c.help_text))}</p><small>${esc(c.path)}</small>`}</div>`).join('');
  $('install-all').disabled = !env.checks.some(c => !c.available && c.auto_install);
  $('python-index').value = env.config.python_index;
  $('tools-path').value = env.config.tools || ''; $('sdk-path').value = env.config.sdk || ''; $('metal-path').value = env.config.metal || '';
  const isMac = env.system === 'Darwin';
  renderAppleDiscovery();
  $('sdk-path').parentElement.hidden = env.system !== 'Windows';
  $('metal-path').parentElement.hidden = env.system !== 'Windows';
  $('platform-note').textContent = t(isMac ? 'macOS checks: Xcode SDKs, Metal and native build tools. Windows cross-compilation tools are not required.' : env.system === 'Windows' ? 'Windows checks: LLVM/lld, iPhoneOS SDK and Windows Metal tools. macOS builds require a Mac.' : 'This host is not supported for application builds.');
  $('data-folder').textContent = t('Data folder: ') + env.data_directory;
  capability(); translateStatic();
}

function renderAppleDiscovery() {
  const windows = env.system === 'Windows', found = env.apple_tools;
  $('sdk-source-label').hidden = !windows;
  $('sdk-source').value = env.config.sdk_source || 'xybp888';
  $('sdk-search-label').hidden = !windows;
  $('sdk-discovery').hidden = !windows;
  $('sdk-search').value = env.config.sdk_search || '';
  if (!windows || !found) return;
  const sdks = found.sdks || [], archives = found.archives || [];
  const sdkReady = env.checks.some(c => c.name === 'sdk' && c.available);
  const options = sdks.map(sdk => `<option value="${esc(sdk.path)}">iPhoneOS ${esc(sdk.version)} · ${esc(sdk.path)}</option>`).join('');
  $('sdk-discovery').innerHTML = `<p class="hint">${esc(t('Searches Downloads, project tools and the optional SDK search folder. Requires a complete iPhoneOS SDK version 26.5 or newer.'))}</p>${options?`<label>${esc(t('Detected iPhoneOS SDKs'))}<select id="detected-sdk"><option value="">${esc(t('Choose an SDK'))}</option>${options}</select></label>`:''}${(!sdkReady ? archives : []).map(path=>`<p class="hint">${esc(path)} <button data-sdk-archive="${esc(path)}">${esc(t('Extract and configure SDK'))}</button></p>`).join('')}${!options&&!archives.length?`<p class="hint">${esc(t('No complete iPhoneOS SDK found. Finish your download, then click Recheck.'))}</p>`:''}`;
  if ($('detected-sdk')) $('detected-sdk').value = env.config.sdk || '';
}
$('sdk-discovery').onchange = action(async e => {
  if (e.target.id !== 'detected-sdk' || !e.target.value) return;
  await api('config', {method:'PUT',body:JSON.stringify({sdk:e.target.value})});
  settingsDirty = false; await loadEnvironment(); message('Settings saved.');
});
$('sdk-discovery').onclick = action(async e => {
  const archive = e.target.dataset.sdkArchive;
  if (!archive) return;
  await api('config', {method:'PUT',body:JSON.stringify({sdk_archive:archive,sdk_source:'local'})});
  await installDependencies(['sdk']);
});
let settingsDirty = false, lastAppleScan = 0;
const installStates = new Map();
async function refresh() {
  if ($('settings').open && env?.system === 'Windows' && !settingsDirty && Date.now() - lastAppleScan > 15000) {
    lastAppleScan = Date.now(); await loadEnvironment();
  }
  const tasks = await api('tasks');
  const changed = tasks.filter(task => task.kind === 'install' && ['succeeded','failed','cancelled','interrupted'].includes(task.status) && installStates.get(task.id) !== task.status);
  for (const task of tasks.filter(task => task.kind === 'install')) installStates.set(task.id, task.status);
  if (changed.length) await loadEnvironment();
  $('tasks').innerHTML = tasks.length ? tasks.map(task => {
    const finished = ['succeeded','failed','cancelled','interrupted'].includes(task.status);
    return `<article class="task"><div><div class="task-title"><span class="badge">${esc(t(task.status))}</span>${esc(t(task.kind))} · ${esc(task.kind === 'install' ? task.dependencies.join(', ') : (task.game || t('Auto detect')))} <small>${new Date(task.created*1000).toLocaleString(uiLanguage)}</small></div><div class="task-stage">${esc(t(task.message || task.stage))}</div></div><div class="actions"><button data-log="${task.id}">Log</button>${finished?`<button data-retry="${task.id}">Retry</button><button data-delete="${task.id}">Delete</button>`:`<button data-cancel="${task.id}">Cancel</button>`}</div><div class="downloads">${task.artifacts.map(name => `<a href="/api/tasks/${task.id}/artifacts/${name.split('/').map(encodeURIComponent).join('/')}">${esc(name)}</a>`).join('')}</div></article>`;
  }).join('') : '<p class="empty">No tasks yetask. Your next build starts above.</p>';
  translateStatic($('tasks'));
  if (logTask && $('logs').open) {
    const result = await api(`tasks/${logTask}/log?offset=${logOffset}`); logOffset = result.offset;
    $('log-text').textContent = ($('log-text').textContent + result.text).slice(-300000);
  }
}
$('files').onchange = action(e => upload(e.target.files));
$('drop').ondragover = e => e.preventDefault();
$('drop').ondrop = action(e => { e.preventDefault(); return upload(e.dataTransfer.files); });
$('import').onclick = action(async () => { const result = await api('import',{method:'POST',body:JSON.stringify({path:$('local-path').value})}); inputs.push(result); renderInputs(); $('local-path').value=''; });
$('inputs').onclick = action(async e => { const id=e.target.dataset.remove; if (!id) return; await api('uploads/'+id,{method:'DELETE'}); inputs=inputs.filter(x=>x.id!==id); renderInputs(); });
$('kind').onchange = $('game').onchange = capability;
$('ios').onchange = $('mac').onchange = capability;
$('start').onclick = action(async () => {
  const keys = inputs.filter(x => x.name.toLowerCase().endsWith('.keys'));
  if (keys.length !== 1) throw new Error('Add exactly one prod.keys file.');
  const targets = ['ios','mac'].filter(x => $(x).checked);
  if ($('kind').value === 'build' && !targets.length) throw new Error('Select at least one output platform.');
  const result = await api('tasks',{method:'POST',body:JSON.stringify({kind:$('kind').value,game:$('game').value,
    files:inputs.filter(x=>!x.name.toLowerCase().endsWith('.keys')).map(x=>x.id),keys:keys[0].id,targets:targets.length?targets:['ios'],retain_keys:$('retain').checked,
    separate_romfs:$('kind').value==='build'&&targets.includes('ios')&&$('separate-romfs').checked,
    settings:{DM_LANG:$('language').value,DM_OPMODE:$('mode').value,DM_METALFX_SPATIAL:$('spatial').value,DM_METALFX_OUTPUT_HEIGHT:$('resolution').value}})});
  message('Task queued: '+result.id.slice(0,8)); await refresh();
});
$('tasks').onclick = action(async e => {
  const d=e.target.dataset;
  if(d.log){logTask=d.log;logOffset=0;$('log-text').textContent='';$('logs').showModal();await refresh();}
  if(d.cancel) await api(`tasks/${d.cancel}/cancel`,{method:'POST'});
  if(d.retry) await api(`tasks/${d.retry}/retry`,{method:'POST'});
  if(d.delete && confirm(t('Delete this task, its copied inputs, cache and outputs? Original imported files remain.'))) await api('tasks/'+d.delete,{method:'DELETE'});
  if(d.cancel||d.retry||d.delete) await refresh();
});
async function installDependencies(names) {
  const result = await api('dependencies/install', {method:'POST', body:JSON.stringify(names ? {names} : {})});
  $('settings').close(); logTask=result.id; logOffset=0; $('log-text').textContent=''; $('logs').showModal(); await refresh();
}
$('checks').onclick = action(async e => {if (e.target.dataset.install) await installDependencies([e.target.dataset.install]);});
$('install-all').onclick = action(() => installDependencies());
$('settings').addEventListener('input', () => { settingsDirty = true; });
$('settings-button').onclick = action(async () => { settingsDirty = false; lastAppleScan = Date.now(); await loadEnvironment(); $('settings').showModal(); });
$('recheck').onclick = action(async () => {await loadEnvironment(); message('Environment refreshed.');});
$('close-settings').onclick = () => $('settings').close();
$('close-logs').onclick = () => $('logs').close();
$('save-settings').onclick = action(async () => {await api('config',{method:'PUT',body:JSON.stringify({tools:$('tools-path').value,sdk:$('sdk-path').value,metal:$('metal-path').value,python_index:$('python-index').value,sdk_search:$('sdk-search').value,sdk_source:$('sdk-source').value})});settingsDirty=false;await loadEnvironment();message('Settings saved.');});
$('ui-language').value = uiLanguage;
translateStatic();
$('ui-language').onchange = action(async () => {uiLanguage = $('ui-language').value; localStorage.setItem('nx-ui-language', uiLanguage); translateStatic(); renderInputs(); await loadEnvironment(); await refresh();});
action(async () => { await api('session',{method:'POST'}); history.replaceState(null,'','/'); token=''; await loadEnvironment(); await refresh(); setInterval(action(refresh),2500); })();
