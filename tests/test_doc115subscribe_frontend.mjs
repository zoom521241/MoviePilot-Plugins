// Synthetic UI contract tests. Run after `npm ci --ignore-scripts` in the plugin ui directory.
// No API, browser, download or remote storage is accessed.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'

const ui = new URL('../plugins.v3/doc115subscribe/ui/', import.meta.url)
const require = createRequire(new URL('package.json', ui))
const vue = require('vue')
// Page / Config 从 src/version.js 导入 UI_BUILD；测试执行器会删掉 import 行，所以在这里注入同一个值
const UI_BUILD = readFileSync(new URL('src/version.js', ui), 'utf8').match(/export const UI_BUILD = '([^']+)'/)[1]

function component(name, api, options = {}) {
  const source = readFileSync(new URL(`src/components/${name}.vue`, ui), 'utf8')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*\r?\n/gm, '')
  const emitted = []
  const lifecycle = {}
  const helpers = { ...vue, inject: () => options.theme || null, onMounted(fn) { lifecycle.mounted = fn }, onBeforeUnmount(fn) { lifecycle.unmount = fn }, onActivated(fn) { lifecycle.activate = fn }, onDeactivated(fn) { lifecycle.deactivate = fn } }
  const names = name === 'Page'
    ? 'doSearch,searchPage,transfer,keyword,searchedKeyword,results,total,page,filterType,filterQuality,filterSubtitle,filterLink,sortBy,busy,resultVersion,close,startQr,checkQr,qrSessionId,qrImage,records,loadRecords,verifyOne,verifying,needsVerify,tab,recordsFilter,recordsMedia,recordsQuery,recordsPage,recordsTotal,prepareTransfer,confirmTransfer,transferRecord,transferTarget,transferSource,transferOpen,transferQuick,transferNote,msg,msgType,resultFeedback,status,stats,statsItems,applyStatsFilter,hasAction,taskAction,runRecordAction,visibleActions,settingsOpen,visibilityChanged,shouldPoll,specTokens,highlightParts,linkHref,darkTheme,organizationSummary,manifestText,loadSubscriptions,fetchSubscriptions,subscriptions,subscriptionNote,subscriptionCacheEmpty,loadStatus,refreshIndex,runSubscribe,jobBusy,runningJobs,confirmState,answerConfirm,deleteRecord,unhideRecord,clearRecords,bulkAction,selected,selectedIds,toggleAll,isTracking,isCompact,orderedRecords,onSearchKey,changePage,changeRecordsPage'
    : 'load,save,cfg,secrets,msg,msgType,close,loadDirectories,directoryOptions,chooseDirectory,directories,darkTheme,rules,validateAll,tencentHint'
  const setup = new Function('helpers', 'suppliedProps', 'suppliedEmit', 'document', 'setTimeout', 'clearTimeout', 'window', 'localStorage', `
    const { computed, inject, reactive, ref, watch, onMounted, onBeforeUnmount, onActivated, onDeactivated } = helpers;
    const UI_BUILD = ${JSON.stringify(UI_BUILD)};
    const defineProps = () => suppliedProps;
    const defineEmits = () => suppliedEmit;
    ${script}
    return { ${names} };
  `)
  const nativeConfirm = () => { throw new Error('window.confirm must not be used') }
  return { ...setup(helpers, { api, model: options.model || {}, ...(options.props || {}) }, (...event) => emitted.push(event), options.document, options.setTimeout || setTimeout, options.clearTimeout || clearTimeout, options.window || { confirm: nativeConfirm }, options.localStorage), emitted, lifecycle }
}

const response = (id, version = 'version-1', total = 1) => ({ code: 0, data: {
  records: [{ record_id: id, title: id }], total, page: 1, page_size: 10, index_version: version,
} })
const deferred = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

test('small video threshold is explicit and saved as an integer including disable zero', async () => {
  const calls = []
  const config = component('Config', { post: async (path, payload) => { calls.push(payload); return { code: 0 } } })
  assert.equal(config.cfg.min_media_size_mb, 10)
  config.cfg.min_media_size_mb = '5'
  await config.save()
  assert.equal(calls[0].min_media_size_mb, 5)
  config.cfg.min_media_size_mb = 0
  await config.save()
  assert.equal(calls[1].min_media_size_mb, 0)
})

test('invalid or blank small video threshold never sends a config write', async () => {
  const calls = []
  const config = component('Config', { post: async (path, payload) => { calls.push(payload); return { code: 0 } } })
  for (const invalid of ['', null, -1, 1.5, 'abc', 1025]) {
    config.cfg.min_media_size_mb = invalid
    await config.save()
    assert.equal(config.msgType.value, 'error')
  }
  assert.equal(calls.length, 0)
})

test('transfer uses displayed resource identity even after input keyword changes', async () => {
  const calls = []
  const page = component('Page', { post: async (path, payload) => {
    calls.push([path, payload])
    return path.endsWith('/search') ? response('resource-tv') : { code: 0, msg: 'ok' }
  } })
  page.keyword.value = 'old name'
  await page.doSearch()
  page.keyword.value = 'unsubmitted new name'
  await page.transfer(page.results.value[0], 'tv')
  assert.deepEqual(calls[1][1], { record_id: 'resource-tv', index_version: 'version-1', to: 'tv' })
  assert.equal(page.searchedKeyword.value, 'old name')
})

test('server filters and page are sent before full total is displayed', async () => {
  const calls = []
  const page = component('Page', { post: async (path, payload) => {
    calls.push(payload)
    return response('matching-result', 'v2', 125)
  } })
  page.filterType.value = 'tv'
  page.filterQuality.value = '4k'
  page.filterLink.value = 'share'
  await vue.nextTick()
  await page.searchPage('locked keyword', 3)
  assert.deepEqual(calls[0], { keyword: 'locked keyword', media_type: 'tv', quality: '4k', subtitle: 'all', link_kind: 'share', page: 3, page_size: 10 })
  assert.equal(page.total.value, 125)
  assert.equal(page.results.value.length, 1)
})

test('per-record verify only asks about that one record', async () => {
  const calls = []
  const page = component('Page', {
    get: async (path, options) => {
      calls.push(['GET', path, options])
      return { code: 0, data: [{ id: 'r1', status: 'organized', title: 'demo' }] }
    },
    post: async (path, payload) => {
      calls.push(['POST', path, payload])
      return { code: 0, data: { checked: 1, confirmed: 1, partial: 0, failed: 0, unfound: 0 } }
    },
  })
  await page.verifyOne({ id: 'r1' })
  assert.equal(calls[0][0], 'POST')
  assert.equal(calls[0][1].endsWith('/records_verify'), true)
  assert.deepEqual(calls[0][2], { id: 'r1' })
  assert.equal(calls.some(([, path]) => String(path).endsWith('/records')), true)
  assert.equal(page.records.value.length, 1)
  assert.equal(page.verifying.r1, false)
})

test('records refresh only reads the list and never triggers a global verify', async () => {
  const calls = []
  const page = component('Page', {
    get: async (path, options) => {
      calls.push(['GET', path, options])
      return { code: 0, data: [] }
    },
    post: async (path, payload) => {
      calls.push(['POST', path, payload])
      return { code: 0 }
    },
  })
  await page.loadRecords()
  assert.equal(calls.length, 1)
  assert.equal(calls[0][0], 'GET')
  assert.equal(calls[0][1].endsWith('/records'), true)
  assert.deepEqual(calls[0][2]?.params, { page: 1, page_size: 10, filter: 'all' })
  assert.equal(page.needsVerify({ status: 'done' }), true)
  assert.equal(page.needsVerify({ status: 'failed' }), false)
  assert.equal(page.needsVerify({ status: 'organized', organization_confirmed: true }), false)
})

test('late search response cannot replace a newer result or its index version', async () => {
  const oldRequest = deferred()
  const newRequest = deferred()
  const page = component('Page', { post: async (path, payload) => payload.keyword === 'old' ? oldRequest.promise : newRequest.promise })
  const oldSearch = page.searchPage('old', 1)
  const newSearch = page.searchPage('new', 1)
  newRequest.resolve(response('new-result', 'new-version'))
  await newSearch
  oldRequest.resolve(response('old-result', 'old-version'))
  await oldSearch
  assert.equal(page.results.value[0].record_id, 'new-result')
  assert.equal(page.resultVersion.value, 'new-version')
  assert.equal(page.busy.search, false)
})

test('same result cannot submit twice while transfer is outstanding', async () => {
  const transferResponse = deferred()
  let submitted = 0
  const page = component('Page', { post: async (path) => {
    if (path.endsWith('/search')) return response('record')
    submitted += 1
    return transferResponse.promise
  } })
  await page.searchPage('test', 1)
  const first = page.transfer(page.results.value[0], 'movie')
  await page.transfer(page.results.value[0], 'tv')
  assert.equal(submitted, 1)
  transferResponse.resolve({ code: 0 })
  await first
})

test('configuration masks legacy plaintext responses and does not report rejected save as success', async () => {
  const config = component('Config', {
    get: async () => ({ code: 0, data: { tencent_cookie: 'synthetic-secret', p115_cookie: 'other-secret' } }),
    post: async () => ({ code: 1, msg: 'invalid cron' }),
  })
  await config.load()
  assert.equal(config.cfg.tencent_cookie, '')
  assert.equal(config.cfg.p115_cookie, '')
  assert.equal(config.secrets.tencent_ready, true)
  await config.save()
  assert.equal(config.msgType.value, 'error')
  assert.match(config.msg.value, /invalid cron/)
  assert.equal(config.emitted.some(([event]) => event === 'save'), false)
})

test('QR start forces a new session and accepts immediate confirmed response', async () => {
  const calls = []
  const page = component('Page', { get: async (path, config) => {
    calls.push([path, config])
    return path.endsWith('/qr_start') ? { code: 0, data: { state: 'confirmed' } } : { code: 0, data: {} }
  } })
  await page.startQr()
  assert.equal(calls[0][1].params.force, true)
  assert.equal(page.qrSessionId.value, '')
  assert.equal(page.busy.qr, false)
  page.close()
})

test('successful config save cannot ask the host to overwrite stored secrets', async () => {
  let payload
  const config = component('Config', {
    get: async () => ({ code: 0, data: { tencent_cookie_ready: true, p115_cookie_ready: false, p115_ready: true } }),
    post: async (path, sent) => { payload = sent; return { code: 0 } },
  })
  await config.load()
  assert.equal(config.secrets.p115_ready, false)
  await config.save()
  assert.equal(payload.tencent_cookie, '')
  assert.equal(payload.p115_cookie, '')
  assert.equal(payload.clear_tencent_cookie, false)
  assert.equal(config.emitted.some(([event]) => event === 'save'), false)
  assert.equal(config.msgType.value, 'success')
})

test('config page exposes a close action that tells the host to dismiss it', async () => {
  const config = component('Config', {
    get: async () => ({ code: 0, data: {} }),
    post: async () => ({ code: 0 }),
  })
  assert.equal(typeof config.close, 'function')
  config.close()
  assert.equal(config.emitted.some(([event]) => event === 'close'), true)
})

test('QR checks do not overlap and pass the visible session identity', async () => {
  const pending = deferred()
  const calls = []
  const page = component('Page', { get: async (path, config) => {
    calls.push([path, config])
    return pending.promise
  } })
  page.qrSessionId.value = 'visible-session'
  const first = page.checkQr(true)
  await page.checkQr(true)
  assert.equal(calls.length, 1)
  assert.equal(calls[0][1].params.session_id, 'visible-session')
  pending.resolve({ code: 0, data: { state: 'wait' } })
  await first
  page.close()
})

function fakeTimers() {
  let id = 0
  const pending = new Map()
  return {
    pending,
    setTimeout(fn, delay) { const key = ++id; pending.set(key, { fn, delay }); return key },
    clearTimeout(key) { pending.delete(key) },
    async fire() { const [key, timer] = pending.entries().next().value; pending.delete(key); await timer.fn(); await vue.nextTick() },
  }
}

test('source confirmation selects the filtered link by original index and allows manual movie/TV target', async () => {
  const calls = []
  const rec = { record_id: 'mixed-row', title: '合成剧集', media_type: 'tv', links: [{ kind: 'http', url: 'https://docs.qq.com/example' }, { kind: '115_share', url: 'https://115.com/s/fake' }, { kind: 'magnet', url: 'magnet:?xt=urn:btih:synthetic' }] }
  const page = component('Page', { post: async (path, payload) => { calls.push([path, payload]); return { code: 0, data: { state: 'queued' } } } })
  page.results.value = [rec]
  page.resultVersion.value = 'v1'
  page.filterLink.value = 'magnet'
  await vue.nextTick()
  page.prepareTransfer(rec)
  assert.equal(page.transferTarget.value, 'tv')
  assert.equal(page.transferSource.value, '2')
  assert.equal(calls.length, 0, 'opening confirmation cannot submit a resource')
  page.transferTarget.value = 'movie'
  await page.confirmTransfer()
  assert.deepEqual(calls[0][1], { record_id: 'mixed-row', index_version: 'v1', to: 'movie', link_kind: 'magnet', link_index: 2 })
  assert.equal(page.msgType.value, 'info')
  assert.match(page.msg.value, /队列/)
  page.close()
})

test('stale confirmation and forbidden source cannot submit', async () => {
  let submits = 0
  const page = component('Page', { post: async () => { submits += 1; return { code: 0 } } })
  const rec = { record_id: 'r', title: '示例', links: [{ kind: '115_share', url: 'https://115.com/s/fake' }, { kind: 'http', url: 'https://docs.qq.com/example' }] }
  page.resultVersion.value = 'old'
  page.prepareTransfer(rec)
  page.resultVersion.value = 'new'
  await page.confirmTransfer()
  assert.equal(submits, 0)
  assert.match(page.msg.value, /索引已变化/)
  await page.transfer(rec, 'movie', 1)
  assert.equal(submits, 0)
  page.prepareTransfer({ ...rec, bundle: true })
  assert.equal(page.transferOpen.value, false)
  page.close()
})

test('action feedback only maps response shapes the backend actually returns', () => {
  const page = component('Page', {})
  for (const [res, expectedType, pattern] of [
    [{ code: 1, msg: '权限不足' }, 'error', /权限不足/],
    [{ code: 0, data: { query_error: 'timeout' } }, 'error', /timeout/],
    [{ code: 0, data: { state: 'queued' } }, 'info', /队列/],
    [{ code: 0, data: { uncertain: true } }, 'warning', /核对转存结果/],
    [{ code: 0, msg: '已隐藏', data: { done: 3, skipped: 1 } }, 'success', /完成 3 条，跳过 1 条/],
    [{ code: 0, data: { done: 0, skipped: 2 } }, 'warning', /跳过 2 条/],
    [{ code: 0, data: {} }, 'info', /fallback/],
  ]) {
    const [message, type] = page.resultFeedback(res, 'fallback')
    assert.equal(type, expectedType)
    assert.match(message, pattern)
  }
  page.close()
})

test('partial verification black box reports the queue and re-reads only the local record endpoint', async () => {
  const calls = []
  const page = component('Page', {
    post: async (path, payload) => { calls.push(['POST', path, payload]); return { code: 0, msg: '已排队核对整理证据，未重新获取', data: { state: 'queued', queued: 1 } } },
    get: async (path) => { calls.push(['GET', path]); return { code: 0, data: { records: [{ id: 'season', acquisition_status: 'done', organization_status: 'partial', organization: { expected: 20, confirmed: 19, failed: 0, missing: 1, manifest_complete: true }, allowed_actions: ['verify'] }], total: 1, page: 1 } } },
  })
  await page.verifyOne({ id: 'season', allowed_actions: ['verify'] })
  assert.equal(page.msgType.value, 'info')
  assert.match(page.msg.value, /未重新获取/)
  assert.deepEqual(calls.map(c => c[1].split('/').pop()), ['records_verify', 'records'])
  assert.match(page.organizationSummary(page.records.value[0]), /19\/20/)
  assert.match(page.manifestText(page.records.value[0]), /19\/20/)
  assert.equal(page.needsVerify({ organization_confirmed: true, allowed_actions: ['verify'] }), true)
  page.close()
})

test('structured permission actions hide unsupported retries and refuse dispatch', async () => {
  let posts = 0
  const page = component('Page', { post: async () => { posts += 1; return { code: 1, msg: '权限不足' } }, get: async () => ({ code: 0, data: [] }) })
  const record = { id: 'r', status: 'failed', allowed_actions: ['verify'] }
  await page.taskAction(record, 'retry_move')
  assert.equal(posts, 0)
  assert.equal(page.hasAction(record, 'retry_move'), false)
  assert.equal(page.hasAction({ allowed_actions: [{ action: 'verify' }] }, 'verify'), true)
  await page.taskAction({ ...record, allowed_actions: ['retry_move'] }, 'retry_move')
  assert.equal(posts, 1)
  assert.equal(page.msgType.value, 'error')
  assert.match(page.msg.value, /权限不足/)
  page.close()
})

test('polling starts only on the visible active task page and stops on hide, deactivation, tab switch and close', async () => {
  const timers = fakeTimers()
  const doc = { visibilityState: 'visible', addEventListener() {}, removeEventListener() {} }
  let reads = 0
  const page = component('Page', { get: async () => { reads += 1; return { code: 0, data: { records: [{ id: 'r', acquisition_status: 'downloading' }], total: 1 } } } }, { document: doc, ...timers })
  assert.equal(page.tab.value, 'search')
  assert.equal(timers.pending.size, 0)
  page.tab.value = 'records'
  await vue.nextTick(); await Promise.resolve(); await vue.nextTick()
  assert.equal(reads, 1)
  assert.equal(timers.pending.size, 1)
  assert.equal([...timers.pending.values()][0].delay, 20000)
  doc.visibilityState = 'hidden'
  page.visibilityChanged()
  assert.equal(timers.pending.size, 0)
  assert.equal(reads, 1)
  doc.visibilityState = 'visible'
  page.visibilityChanged()
  await Promise.resolve(); await vue.nextTick()
  assert.equal(reads, 2)
  page.lifecycle.deactivate()
  assert.equal(timers.pending.size, 0)
  assert.equal(page.shouldPoll(), false)
  page.lifecycle.activate()
  await Promise.resolve(); await vue.nextTick()
  page.tab.value = 'search'
  await vue.nextTick()
  assert.equal(timers.pending.size, 0)
  page.close()
  assert.equal(timers.pending.size, 0)
})

test('filters debounce and abort the old request while late responses cannot win', async () => {
  const timers = fakeTimers(), old = deferred()
  const calls = []
  const page = component('Page', { post: async (path, payload, options) => { calls.push({ payload, options }); return calls.length === 1 ? old.promise : response('filtered', 'v2') } }, timers)
  const pending = page.searchPage('合成标题', 1)
  page.filterType.value = 'tv'
  await vue.nextTick()
  assert.equal(calls[0].options.signal.aborted, true)
  page.filterQuality.value = '4k'
  page.filterSubtitle.value = 'cn'
  await vue.nextTick()
  assert.equal(calls.length, 1)
  assert.equal(timers.pending.size, 1)
  assert.equal([...timers.pending.values()][0].delay, 220)
  await timers.fire(); await Promise.resolve(); await vue.nextTick()
  old.resolve(response('old', 'old-v'))
  await pending
  assert.equal(calls.length, 2)
  assert.equal(calls[1].payload.subtitle, 'cn')
  assert.equal(calls[1].payload.quality, '4k')
  assert.equal(page.results.value[0].record_id, 'filtered')
  page.close()
})

test('theme responds to host dark boolean including a custom theme name', () => {
  const theme = { current: vue.ref({ dark: false }), name: vue.ref('glass') }
  const page = component('Page', {}, { theme })
  assert.equal(page.darkTheme.value, false)
  theme.current.value = { dark: true }
  assert.equal(page.darkTheme.value, true)
  page.close()
})

test('link protocols reject unsafe or cross-site URLs', () => {
  const page = component('Page', {})
  for (const url of ['javascript:alert(1)', 'data:text/html,unsafe', '//evil.example', 'file:///test']) assert.equal(page.linkHref(url), undefined)
  assert.equal(page.linkHref('magnet:?xt=urn:btih:synthetic'), 'magnet:?xt=urn:btih:synthetic')
  assert.equal(page.linkHref('115.com/s/abc'), 'https://115.com/s/abc')
  page.close()
})

test('local subscription preview neither invokes synchronize nor submits files', async () => {
  const calls = []
  const page = component('Page', { get: async path => { calls.push(path); return { code: 0, data: { subscriptions: [{ title: '合成订阅', matched: false, reason: '缺少可评估发布信息' }], message: '本地快照' } } }, post: async () => { throw new Error('forbidden write') } })
  await page.loadSubscriptions()
  assert.equal(calls.length, 1)
  assert.equal(calls[0].endsWith('/subscriptions_preview'), true)
  assert.equal(page.subscriptions.value[0].reason, '缺少可评估发布信息')
  page.close()
})

test('MP directory selection only accepts cached 115 download paths and leaves other storage untouched', async () => {
  const config = component('Config', { get: async () => ({ code: 0, data: { directories: [{ storage: 'u115', path: '/合成/电影', media_type: 'movie', monitored: true }, { storage: 'local', path: '/unrelated', media_type: 'movie' }] } }) })
  await config.loadDirectories()
  assert.equal(config.directoryOptions('movie').length, 1)
  config.chooseDirectory('movie', '/unrelated')
  assert.notEqual(config.cfg.movie_path, '/unrelated')
  config.chooseDirectory('movie', '/合成/电影')
  assert.equal(config.cfg.movie_path, '/合成/电影')
  assert.equal(config.cfg.subscribe_enabled, false, 'new installation must not enable automatic acquisitions')
})

test('semantic field colours are self-contained, distinct, and readable against both plugin surfaces', () => {
  const css = readFileSync(new URL('src/styles/doc115.css', ui), 'utf8')
  const blocks = [...css.matchAll(/--doc115-surface: (#[0-9a-f]{6});([\s\S]*?)(?=\n})/g)]
  assert.equal(blocks.length, 2)
  function luminance(hex) { const rgb = hex.match(/[0-9a-f]{2}/gi).map(x => parseInt(x, 16) / 255).map(x => x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4); return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] }
  function contrast(a, b) { const values = [luminance(a), luminance(b)].sort((x, y) => y - x); return (values[0] + 0.05) / (values[1] + 0.05) }
  for (const block of blocks) {
    const tokens = Object.fromEntries([...block[2].matchAll(/--doc115-(\w+(?:-\w+)*): (#[0-9a-f]{6});/g)].map(m => [m[1], m[2]]))
    const fields = ['blue', 'purple', 'cyan', 'amber', 'green', 'red', 'orange', 'brown', 'neutral']
    assert.equal(new Set(fields.map(key => tokens[key])).size, fields.length)
    for (const key of fields) for (const background of [block[1], tokens['chip-bg']]) assert.ok(contrast(tokens[key], background) >= 4.5, `${key} must have sufficient contrast against ${background}`)
  }
  const page = component('Page', {})
  assert.deepEqual(page.specTokens('4K 中文字幕 1080P 无中字').filter(t => t.color).map(t => t.color), ['doc115-amber', 'doc115-green', 'doc115-amber', 'doc115-red'])
  const source = readFileSync(new URL('src/components/Page.vue', ui), 'utf8')
  assert.doesNotMatch(source, /(?:text-|bg-)(?:green|red|amber|purple|orange|cyan|brown)-/)
  assert.doesNotMatch(css, /(?:^|\n)\.record-row(?:[\s.{-])/, 'must not leak generic host styles')
  page.close()
})

test('both Vue SFCs compile including templates and responsive classes', () => {
  const { parse, compileScript, compileTemplate } = require('@vue/compiler-sfc')
  for (const name of ['Page', 'Config']) {
    const filename = `src/components/${name}.vue`
    const { descriptor, errors } = parse(readFileSync(new URL(filename, ui), 'utf8'))
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: `doc115-${name}` })
    const template = compileTemplate({ source: descriptor.template.content, filename, id: `doc115-${name}`, compilerOptions: { bindingMetadata: script.bindings } })
    assert.deepEqual(template.errors, [])
  }
})

test('verify black box gives explicit outcomes for queued, rejected and query error responses', async () => {
  for (const [res, expectedType] of [[{ code: 0, data: { state: 'queued' } }, 'info'], [{ code: 1, msg: '任务不存在' }, 'error'], [{ code: 0, data: { query_error: 'HTTP 503' } }, 'error']]) {
    const calls = []
    const page = component('Page', { post: async path => { calls.push(path); return res }, get: async path => { calls.push(path); return { code: 0, data: [] } } })
    await page.verifyOne({ id: 'synthetic' })
    assert.equal(page.msgType.value, expectedType)
    assert.deepEqual(calls.map(p => p.split('/').pop()), ['records_verify', 'records'])
    assert.equal(page.verifying.synthetic, false)
    page.close()
  }
})

test('unchanged task snapshots and failed list reads back off rather than polling every 20 seconds forever', async () => {
  const timers = fakeTimers()
  let fail = false
  const page = component('Page', { get: async () => fail ? { code: 1, msg: 'synthetic timeout' } : { code: 0, data: { records: [{ id: 'r', acquisition_status: 'downloading', progress: 50 }], total: 1 } } }, timers)
  page.tab.value = 'records'
  await vue.nextTick(); await Promise.resolve(); await vue.nextTick()
  assert.equal([...timers.pending.values()][0].delay, 20000)
  await timers.fire()
  assert.equal([...timers.pending.values()][0].delay, 40000)
  await timers.fire()
  assert.equal([...timers.pending.values()][0].delay, 80000)
  fail = true
  await timers.fire()
  // 失败时还会挂一个 6 秒的提示消失计时器；任务轮询计时器仍然退避
  assert.ok([...timers.pending.values()].some(t => t.delay >= 40000))
  assert.equal(page.msgType.value, 'error')
  page.close()
})

test('backend flattened organization counts preserve deleted episode and required-manifest facts', () => {
  const page = component('Page', {})
  const record = { acquisition_status: 'saved', organization_status: 'partial', organized_count: 19, organized_total: 20, organized_missing: 1, organized_failed: 0, manifest_complete: true, allowed_actions: ['verify'] }
  assert.match(page.organizationSummary(record), /19\/20.*1 个待核实/)
  assert.match(page.manifestText(record), /完整.*19\/20.*1 个暂无整理证据/)
  page.close()
})

test('UI version constant is shared by Page/Config and stays in step with package versions', () => {
  const page = readFileSync(new URL('src/components/Page.vue', ui), 'utf8')
  const config = readFileSync(new URL('src/components/Config.vue', ui), 'utf8')
  const manifest = JSON.parse(readFileSync(new URL('../../../package.v3.json', ui), 'utf8'))
  const uiPackage = JSON.parse(readFileSync(new URL('package.json', ui), 'utf8'))
  for (const source of [page, config]) {
    assert.match(source, /import \{ UI_BUILD \} from '\.\.\/version\.js'/)
    assert.doesNotMatch(source, /const UI_BUILD =|前端 v\d/, 'version must not be hard-coded in a component')
  }
  assert.equal(uiPackage.version, UI_BUILD)
  // 后端由同事并行升版：package.v3.json 只允许等于 UI_BUILD，或仍是上一个版本（尚未合并后端）
  const backend = String(manifest.Doc115Subscribe.version)
  assert.equal(backend, UI_BUILD, `package.v3.json ${backend} vs UI ${UI_BUILD}`)
})

// ---- 0.11.0 ----
const flush = async () => { for (let i = 0; i < 6; i += 1) { await Promise.resolve(); await vue.nextTick() } }

test('a reload requested while records are loading is replayed after the current request', async () => {
  const first = deferred()
  const calls = []
  const page = component('Page', { get: async (path, options) => { calls.push(options.params); return calls.length === 1 ? first.promise : { code: 0, data: { records: [{ id: 'fresh' }], total: 1, page: 1 } } } })
  const pending = page.loadRecords()
  assert.equal(await page.loadRecords(), false)
  assert.equal(calls.length, 1)
  first.resolve({ code: 0, data: { records: [{ id: 'stale' }], total: 1, page: 1 } })
  await pending; await flush()
  assert.equal(calls.length, 2, 'pending reload must run once the first request finishes')
  assert.equal(page.records.value[0].id, 'fresh')
  page.close()
})

test('records page follows the backend and falls back to the last page when out of range', async () => {
  const calls = []
  const page = component('Page', { get: async (path, options) => {
    calls.push(options.params.page)
    return options.params.page > 2 ? { code: 0, data: { records: [], total: 15, page: options.params.page } } : { code: 0, data: { records: [{ id: 'p2' }], total: 15, page: 2 } }
  } })
  page.recordsPage.value = 5
  await page.loadRecords(); await flush()
  assert.deepEqual(calls, [5, 2])
  assert.equal(page.recordsPage.value, 2)
  assert.equal(page.records.value[0].id, 'p2')
  page.close()
})

test('records query, media and hidden filters are sent only when set and the query is debounced', async () => {
  const timers = fakeTimers()
  const calls = []
  const page = component('Page', { get: async (path, options) => { calls.push(options.params); return { code: 0, data: { records: [], total: 0, page: 1 } } } }, timers)
  page.tab.value = 'records'
  await flush()
  assert.deepEqual(calls.at(-1), { page: 1, page_size: 10, filter: 'all' })
  page.recordsQuery.value = '合成'
  await vue.nextTick()
  const debounce = [...timers.pending.values()].find(t => t.delay === 400)
  assert.ok(debounce, 'query must debounce 400ms')
  const before = calls.length
  await debounce.fn(); await flush()
  assert.equal(calls.length, before + 1)
  assert.deepEqual(calls.at(-1), { page: 1, page_size: 10, filter: 'all', q: '合成' })
  page.recordsMedia.value = 'tv'
  page.recordsFilter.value = 'hidden'
  await flush()
  assert.equal(calls.at(-1).media, 'tv')
  assert.equal(calls.at(-1).filter, 'hidden')
  page.close()
})

test('global stats come from status, load on mount and stat chips switch the task filter', async () => {
  const gets = []
  const page = component('Page', { get: async path => { gets.push(path.split('/').pop()); return path.endsWith('/status') ? { code: 0, data: { stats: { movie: { total: 3, organized: 1 }, tv: { total: 2, organized: 0 }, total: 5, organized: 1, active: 1, attention: 2 } } } : { code: 0, data: { records: [], total: 0, page: 1, stats: { total: 0 } } } } })
  await page.lifecycle.mounted(); await flush()
  assert.equal(gets[0], 'status')
  assert.equal(page.stats.value.total, 5)
  assert.deepEqual(page.statsItems.value.map(i => i.key), ['movie', 'tv', 'completed', 'active', 'needs_attention', 'all'])
  page.applyStatsFilter('tv')
  assert.equal(page.tab.value, 'records')
  assert.equal(page.recordsMedia.value, 'tv')
  assert.equal(page.recordsFilter.value, 'all')
  page.applyStatsFilter('needs_attention')
  assert.equal(page.recordsFilter.value, 'needs_attention')
  assert.equal(page.recordsMedia.value, 'all')
  await flush()
  assert.equal(page.stats.value.total, 5, 'filtered records stats must not replace the global stats')
  page.lifecycle.unmount()
})

test('hiding uses the shared dialog, is refused for tracked tasks and unhide goes through records_bulk', async () => {
  const posts = []
  const page = component('Page', { post: async (path, payload) => { posts.push([path.split('/').pop(), payload]); return { code: 0, data: { done: 1, skipped: 0 } } }, get: async () => ({ code: 0, data: { records: [], total: 0, page: 1 } }) })
  await page.deleteRecord({ id: 't', title: '跟踪中', tracking: true })
  assert.equal(posts.length, 0)
  assert.match(page.msg.value, /先停止跟踪/)
  assert.equal(page.isTracking({ allowed_actions: ['stop_tracking'] }), true, 'legacy records infer tracking from allowed actions')
  const pending = page.deleteRecord({ id: 'h', title: '已结束', tracking: false })
  await flush()
  assert.equal(page.confirmState.open, true)
  assert.match(page.confirmState.text, /仅从列表隐藏.*『已隐藏』筛选中恢复/)
  page.answerConfirm(true)
  await pending
  assert.deepEqual(posts[0], ['records_delete', { id: 'h' }])
  await page.unhideRecord({ id: 'h', title: '已结束', hidden: true })
  assert.deepEqual(posts[1], ['records_bulk', { ids: ['h'], action: 'unhide' }])
  page.close()
})

test('cancelled confirmation sends nothing and clearing reports hidden / skipped counts', async () => {
  const posts = []
  const page = component('Page', { post: async (path, payload) => { posts.push(payload); return { code: 0, data: { hidden: 4, skipped: 2 } } }, get: async () => ({ code: 0, data: { records: [], total: 0, page: 1 } }) })
  const cancelled = page.clearRecords(); await flush()
  page.answerConfirm(false); await cancelled
  assert.equal(posts.length, 0)
  const accepted = page.clearRecords(); await flush()
  page.answerConfirm(true); await accepted
  assert.deepEqual(posts[0], {})
  assert.match(page.msg.value, /已隐藏 4 条，跟踪中的 2 条保留/)
  page.close()
})

test('bulk actions confirm once, send the selected ids and clear the selection', async () => {
  const posts = []
  const rows = [{ id: 'a', title: 'A' }, { id: 'b', title: 'B' }]
  const page = component('Page', { post: async (path, payload) => { posts.push([path.split('/').pop(), payload]); return { code: 0, msg: '批量', data: { done: 2, skipped: 0 } } }, get: async () => ({ code: 0, data: { records: rows, total: 2, page: 1 } }) })
  await page.loadRecords(); await flush()
  page.toggleAll(true)
  assert.deepEqual(page.selectedIds.value, ['a', 'b'])
  const pending = page.bulkAction('stop_tracking'); await flush()
  assert.equal(page.confirmState.tone, 'danger')
  page.answerConfirm(true); await pending
  assert.deepEqual(posts, [['records_bulk', { ids: ['a', 'b'], action: 'stop_tracking' }]])
  assert.equal(page.selectedIds.value.length, 0)
  assert.match(page.msg.value, /完成 2 条/)
  page.close()
})

test('reconcile runs directly while confirm_saved needs the checked second confirmation', async () => {
  const posts = []
  const page = component('Page', { post: async (path, payload) => { posts.push(payload); return { code: 0, data: { state: 'queued' } } }, get: async () => ({ code: 0, data: [] }) })
  const r = { id: 'u', title: '待核实', allowed_actions: ['reconcile', 'confirm_saved', 'stop_tracking'] }
  assert.deepEqual(page.visibleActions(r).map(a => a.action), ['reconcile', 'confirm_saved', 'stop_tracking'])
  await page.runRecordAction(r, 'reconcile')
  assert.deepEqual(posts[0], { id: 'u', action: 'reconcile' })
  const pending = page.runRecordAction(r, 'confirm_saved'); await flush()
  assert.match(page.confirmState.text, /仅当你已在 115 中确认文件存在时使用/)
  assert.ok(page.confirmState.check, 'confirm_saved must require an explicit checkbox')
  page.answerConfirm(true); await pending
  assert.deepEqual(posts[1], { id: 'u', action: 'confirm_saved' })
  await page.runRecordAction({ ...r, allowed_actions: [] }, 'confirm_saved')
  assert.equal(posts.length, 2)
  page.close()
})

test('expired QR status clears the session and image even when the backend answers code 1', async () => {
  const page = component('Page', { get: async () => ({ code: 1, msg: '二维码已失效', data: { state: 'expired' } }) })
  page.qrSessionId.value = 'old'
  page.qrImage.value = 'data:image/png;base64,AAAA'
  await page.checkQr(true)
  assert.equal(page.qrSessionId.value, '')
  assert.equal(page.qrImage.value, '')
  assert.equal(page.msgType.value, 'warning')
  assert.match(page.msg.value, /重新获取/)
  page.close()
})

test('index refresh polls status every 5 seconds while the job runs and reports the final result', async () => {
  const timers = fakeTimers()
  const states = ['queued', 'running', 'failed']
  let reads = 0
  const page = component('Page', {
    post: async () => ({ code: 0, msg: '已排队后台处理', data: { state: 'queued' } }),
    get: async () => { const state = states[Math.min(reads, states.length - 1)]; reads += 1; return { code: 0, data: { jobs: { index: { state, msg: state === 'failed' ? '腾讯文档 Cookie 失效' : '', at: 1 } } } } },
  }, timers)
  await page.refreshIndex()
  assert.equal(page.jobBusy('index'), true)
  assert.match(page.runningJobs.value[0].label, /索引更新/)
  const poll = () => [...timers.pending.entries()].find(([, t]) => t.delay === 5000)
  assert.ok(poll(), 'must poll status every 5 seconds')
  let [key, timer] = poll(); timers.pending.delete(key); await timer.fn(); await flush()
  assert.equal(page.jobBusy('index'), true)
  ;[key, timer] = poll(); timers.pending.delete(key); await timer.fn(); await flush()
  assert.equal(page.jobBusy('index'), false)
  assert.equal(poll(), undefined, 'polling stops after the job finishes')
  assert.equal(page.msgType.value, 'error')
  assert.match(page.msg.value, /Cookie 失效/)
  assert.doesNotMatch(page.msg.value, /文档索引已更新。/)
  page.close()
})

test('subscription preview shows the empty-cache state and keeps year / qtext / next check', async () => {
  const empty = component('Page', { get: async () => ({ code: 0, data: { records: [], cache_empty: true, cached_at: 0 } }) })
  await empty.loadSubscriptions()
  assert.equal(empty.subscriptionCacheEmpty.value, true)
  const full = component('Page', { get: async () => ({ code: 0, data: { records: [{ title: '合成', year: '2026', qtext: '4K', next_check_at: '2026-10-10 21:00', matched: 1 }], cache_empty: false, cached_at: 1791600000 } }) })
  await full.loadSubscriptions()
  assert.equal(full.subscriptionCacheEmpty.value, false)
  assert.deepEqual([full.subscriptions.value[0].year, full.subscriptions.value[0].qtext], ['2026', '4K'])
  assert.match(full.subscriptionNote.value, /更新于/)
  const source = readFileSync(new URL('src/components/Page.vue', ui), 'utf8')
  assert.match(source, /读取 MP 订阅并预演/)
  assert.match(source, /下次自动同步/)
  // 不再在空状态里重复放「同步并获取匹配资源」按钮
  assert.equal((source.match(/@click="runSubscribe"/g) || []).length, 1)
})

test('read-only subscription fetch calls subscriptions_fetch then reloads the preview', async () => {
  const calls = []
  const page = component('Page', {
    post: async (path) => { calls.push(['post', path]); return { code: 0, msg: '已读取 MP 订阅 3 个（电影 2 个），未提交任何资源' } },
    get: async (path) => { calls.push(['get', path]); return { code: 0, data: { records: [], cache_empty: false, cached_at: 1 } } },
  })
  await page.fetchSubscriptions()
  assert.deepEqual(calls.map(([m, p]) => [m, p.split('/').pop()]), [['post', 'subscriptions_fetch'], ['get', 'subscriptions_preview']])
  assert.match(page.msg.value, /未提交任何资源/)
})

test('close only notifies the host; reactivation after deactivation keeps the component working', async () => {
  let reads = 0
  const page = component('Page', { get: async path => { if (path.endsWith('/records')) reads += 1; return { code: 0, data: { records: [], total: 0, page: 1 } } } })
  page.close()
  assert.equal(page.emitted.some(([event]) => event === 'close'), true)
  page.tab.value = 'records'
  await flush()
  assert.equal(reads, 1, 'close must not permanently dispose the page')
  page.lifecycle.deactivate()
  page.lifecycle.activate()
  await flush()
  assert.equal(reads, 2)
  page.lifecycle.unmount()
})

test('search sends sort only when not relevance, remembers filters, keeps old results while paging and ignores IME enter', async () => {
  const store = new Map([['doc115subscribe.search.v1', JSON.stringify({ type: 'tv', sort: 'year_desc' })]])
  const localStorage = { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) }
  const later = deferred()
  const calls = []
  const page = component('Page', { post: async (path, payload) => { calls.push(payload); return calls.length === 2 ? later.promise : response('r' + calls.length, 'v', 25) } }, { localStorage })
  assert.equal(page.filterType.value, 'tv')
  assert.equal(page.sortBy.value, 'year_desc')
  page.keyword.value = '合成'
  page.onSearchKey({ isComposing: true })
  assert.equal(calls.length, 0)
  page.onSearchKey({ isComposing: false })
  await flush()
  assert.equal(calls[0].sort, 'year_desc')
  assert.equal(calls[0].media_type, 'tv')
  const paging = page.searchPage('合成', 2)
  assert.equal(page.results.value[0].record_id, 'r1', 'old results stay visible while the next page loads')
  later.resolve(response('r2', 'v', 25)); await paging
  page.sortBy.value = 'relevance'
  page.filterQuality.value = '4k'
  await vue.nextTick()
  assert.deepEqual(JSON.parse(store.get('doc115subscribe.search.v1')), { type: 'tv', quality: '4k', subtitle: 'all', link: 'all', sort: 'relevance' })
  page.close()
  const broken = component('Page', {}, { localStorage: { getItem() { throw new Error('denied') }, setItem() { throw new Error('denied') } } })
  assert.equal(broken.sortBy.value, 'relevance')
  broken.filterType.value = 'movie'
  await vue.nextTick()
  broken.close()
})

test('disabled plugin blocks search; highlight prefers backend match and is case-insensitive', async () => {
  let posts = 0
  const page = component('Page', { post: async () => { posts += 1; return response('x') } })
  page.status.enabled = false
  page.keyword.value = 'abc'
  await page.doSearch()
  assert.equal(posts, 0)
  assert.match(page.msg.value, /停用/)
  page.searchedKeyword.value = 'matrix'
  assert.deepEqual(page.highlightParts('The MATRIX Reloaded').filter(p => p.hit).map(p => p.text), ['MATRIX'])
  assert.deepEqual(page.highlightParts('黑客帝国 矩阵', '帝国').filter(p => p.hit).map(p => p.text), ['帝国'])
  assert.deepEqual(page.highlightParts('a.b(c)', '.b(').filter(p => p.hit).map(p => p.text), ['.b('])
  page.close()
})

test('single-source cards open a pre-filled quick confirmation; magnet note explains staging and subdir', () => {
  const page = component('Page', {})
  page.resultVersion.value = 'v1'
  const rec = { record_id: 'm', title: '合成', media_type: 'movie', links: [{ kind: 'http', url: 'https://docs.qq.com/x' }, { kind: 'magnet', url: 'magnet:?xt=urn:btih:x' }] }
  page.prepareTransfer(rec, true)
  assert.equal(page.transferOpen.value, true, 'quick acquire still asks for confirmation')
  assert.equal(page.transferQuick.value, true)
  assert.equal(page.transferSource.value, '1')
  assert.equal(page.transferTarget.value, 'movie')
  assert.match(page.transferNote.value, /暂存目录.*片名 \(年份\).*以插件设置为准/)
  const source = readFileSync(new URL('src/components/Page.vue', ui), 'utf8')
  assert.match(source, /transferTarget\.value === 'tv' \? \(status\.tv_path \|\| '[^']+'\) : \(status\.movie_path \|\| '[^']+'\)/)
  page.close()
})

test('message auto-dismisses after 6 seconds', async () => {
  const timers = fakeTimers()
  const page = component('Page', { get: async () => ({ code: 0, data: { records: [], total: 0, page: 1 } }) }, timers)
  await page.doSearch()
  assert.match(page.msg.value, /请输入/)
  const timer = [...timers.pending.values()].find(t => t.delay === 6000)
  assert.ok(timer)
  timer.fn()
  assert.equal(page.msg.value, '')
  page.close()
})

test('records order puts attention and active tasks first; finished tasks become compact rows', async () => {
  const rows = [
    { id: 'done', acquisition_status: 'saved', organization_status: 'success' },
    { id: 'dl', acquisition_status: 'downloading', organization_status: 'pending' },
    { id: 'bad', acquisition_status: 'failed', organization_status: 'not_applicable' },
  ]
  const page = component('Page', { get: async () => ({ code: 0, data: { records: rows, total: 3, page: 1 } }) })
  await page.loadRecords()
  assert.deepEqual(page.orderedRecords.value.map(r => r.id), ['bad', 'dl', 'done'])
  assert.equal(page.isCompact(rows[0]), true)
  assert.equal(page.isCompact(rows[1]), false)
  page.close()
})

test('config validates fields live and refuses to save invalid values', async () => {
  const posts = []
  const config = component('Config', { post: async (path, payload) => { posts.push(payload); return { code: 0 } } })
  const { rules } = config
  assert.notEqual(rules.docUrl(''), true)
  assert.notEqual(rules.docUrl('https://example.com/sheet/abc'), true)
  assert.equal(rules.docUrl('https://docs.qq.com/sheet/DZWtEeFFGZW9XUkJo'), true)
  assert.equal(rules.cron('0 6 * * *'), true)
  assert.equal(rules.cron('*/15 1-5 * * mon-fri'), true)
  assert.notEqual(rules.cron('0 6 * *'), true)
  assert.notEqual(rules.path('115/电影'), true)
  assert.notEqual(rules.path('/a/../b'), true)
  config.cfg.movie_path = '/115/电影'
  config.cfg.tv_path = '/115/电视剧'
  assert.notEqual(rules.staging('/115/电影'), true)
  assert.notEqual(rules.staging('/115/电影/磁力'), true)
  assert.notEqual(rules.staging('/115'), true)
  assert.equal(rules.staging('/115/暂存'), true)
  config.cfg.magnet_staging_path = '/115/电影/'
  await config.save()
  assert.equal(posts.length, 0)
  assert.equal(config.msgType.value, 'error')
  assert.match(config.msg.value, /暂存目录/)
})

test('config save refills normalised values returned by the backend', async () => {
  const config = component('Config', { post: async () => ({ code: 0, msg: '配置已保存', data: { movie_path: '/115/电影', tv_path: '/115/电视剧', magnet_staging_path: '/115/暂存', tencent_cookie: '', tencent_cookie_ready: true, p115_cookie_ready: false } }) })
  config.cfg.movie_path = '/115/电影/'
  config.cfg.tv_path = '/115/电视剧'
  config.cfg.magnet_staging_path = '/115/暂存'
  await config.save()
  assert.equal(config.msgType.value, 'success')
  assert.equal(config.cfg.movie_path, '/115/电影')
  assert.equal(config.secrets.tencent_ready, true)
})

test('embedded config does not tell the user to open the settings it is already in', () => {
  const embedded = component('Config', {}, { props: { embedded: true } })
  assert.doesNotMatch(embedded.tencentHint.value, /插件页面「设置」/)
  assert.match(embedded.tencentHint.value, /扫码登录腾讯文档/)
  const standalone = component('Config', {})
  assert.match(standalone.tencentHint.value, /插件详情页/)
})

test('templates drop native selects, window.confirm, removed routes and dead MP history code', () => {
  for (const name of ['Page', 'Config', 'ConfirmDialog']) {
    const source = readFileSync(new URL(`src/components/${name}.vue`, ui), 'utf8')
    assert.doesNotMatch(source, /<select[\s>]/, `${name} must use v-select / chip groups`)
    assert.doesNotMatch(source, /window\.confirm/)
    assert.doesNotMatch(source, /check_organization|cancel_task|retry_task|verify_organization|mp_history|safeMpUrl|mp_url|kindName|kindColor|last_refresh/)
  }
  const page = readFileSync(new URL('src/components/Page.vue', ui), 'utf8')
  assert.match(page, /aria-label="搜索结果跳转页码"/)
  assert.match(page, /aria-label="任务列表跳转页码"/)
  assert.match(page, /@keydown\.enter="onSearchKey"/)
  assert.match(page, /v-if="total > 0 && pageCount > 1"/)
  const config = readFileSync(new URL('src/components/Config.vue', ui), 'utf8')
  assert.match(config, /aria-label="关闭设置"/)
  assert.doesNotMatch(config.match(/magnet_staging_path"[^>]*>/)[0], /\shide-details(?!=)/)
  for (const group of ['腾讯文档', '115 网盘', '保存目录', '电影订阅', '高级']) assert.match(config, new RegExp(`<v-expansion-panel-title>${group}`))
  const app = readFileSync(new URL('src/App.vue', ui), 'utf8')
  assert.match(app, /<style scoped>/)
})

test('ConfirmDialog compiles and follows the plugin theme when teleported', () => {
  const { parse, compileScript, compileTemplate } = require('@vue/compiler-sfc')
  const filename = 'src/components/ConfirmDialog.vue'
  const source = readFileSync(new URL(filename, ui), 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'doc115-confirm' })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename, id: 'doc115-confirm', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  assert.match(source, /:data-doc115-theme="dark \? 'dark' : 'light'"/)
})
