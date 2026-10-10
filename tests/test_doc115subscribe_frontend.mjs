// Synthetic UI contract tests. Run after `npm ci --ignore-scripts` in the plugin ui directory.
// No API, browser, download or remote storage is accessed.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'

const ui = new URL('../plugins.v3/doc115subscribe/ui/', import.meta.url)
const require = createRequire(new URL('package.json', ui))
const vue = require('vue')

function component(name, api, options = {}) {
  const source = readFileSync(new URL(`src/components/${name}.vue`, ui), 'utf8')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*\r?\n/gm, '')
  const emitted = []
  const lifecycle = {}
  const helpers = { ...vue, inject: () => options.theme || null, onMounted(fn) { lifecycle.mounted = fn }, onBeforeUnmount(fn) { lifecycle.unmount = fn }, onActivated(fn) { lifecycle.activate = fn }, onDeactivated(fn) { lifecycle.deactivate = fn } }
  const names = name === 'Page'
    ? 'doSearch,searchPage,transfer,keyword,searchedKeyword,results,total,page,filterType,filterQuality,filterSubtitle,filterLink,busy,resultVersion,close,startQr,checkQr,qrSessionId,records,loadRecords,verifyOne,verifying,needsVerify,tab,recordsFilter,recordsPage,recordsTotal,prepareTransfer,confirmTransfer,transferRecord,transferTarget,transferSource,transferOpen,msg,msgType,resultFeedback,status,hasAction,taskAction,settingsOpen,visibilityChanged,shouldPoll,specTokens,linkHref,safeMpUrl,darkTheme,organizationSummary,manifestText,loadSubscriptions,subscriptions,subscriptionNote'
    : 'load,save,cfg,secrets,msg,msgType,close,loadDirectories,directoryOptions,chooseDirectory,directories,darkTheme'
  const setup = new Function('helpers', 'suppliedProps', 'suppliedEmit', 'document', 'setTimeout', 'clearTimeout', 'window', `
    const { computed, inject, reactive, ref, watch, onMounted, onBeforeUnmount, onActivated, onDeactivated } = helpers;
    const defineProps = () => suppliedProps;
    const defineEmits = () => suppliedEmit;
    ${script}
    return { ${names} };
  `)
  return { ...setup(helpers, { api, model: options.model || {} }, (...event) => emitted.push(event), options.document, options.setTimeout || setTimeout, options.clearTimeout || clearTimeout, options.window || { confirm: () => true }), emitted, lifecycle }
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

test('white box action feedback covers success, failure, partial, query error, unknown, queued, paused and skipped', () => {
  const page = component('Page', {})
  for (const [data, expectedType, pattern] of [
    [{ confirmed: 20 }, 'success', /MP\s*整理成功/],
    [{ failed: 1 }, 'error', /失败项目/],
    [{ partial: 1 }, 'warning', /部分完成/],
    [{ query_error: 'timeout' }, 'error', /查询失败/],
    [{ unfound: 1 }, 'warning', /不能据此判断文件丢失/],
    [{ state: 'queued' }, 'info', /队列/],
    [{ paused: true }, 'warning', /暂停/],
    [{ skipped: 1 }, 'info', /无需/],
  ]) {
    const [message, type] = page.resultFeedback({ code: 0, data }, 'fallback')
    assert.equal(type, expectedType)
    assert.match(message, pattern)
    assert.doesNotMatch(message, /已整理入库|后台会继续自动核对/)
  }
  assert.equal(page.resultFeedback({ code: 0, data: { query_errors: [] } }, 'ok')[1], 'info')
  page.close()
})

test('partial verification black box displays warning and re-reads only the local record endpoint', async () => {
  const calls = []
  const page = component('Page', {
    post: async (path, payload) => { calls.push(['POST', path, payload]); return { code: 0, data: { partial: 1 } } },
    get: async (path) => { calls.push(['GET', path]); return { code: 0, data: { records: [{ id: 'season', acquisition_status: 'done', organization_status: 'partial', organization: { expected: 20, confirmed: 19, failed: 0, missing: 1, manifest_complete: true }, allowed_actions: ['verify'] }], total: 1, page: 1 } } },
  })
  await page.verifyOne({ id: 'season', allowed_actions: ['verify'] })
  assert.equal(page.msgType.value, 'warning')
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

test('link protocols and MP navigation reject unsafe or cross-site URLs', () => {
  const page = component('Page', {})
  for (const url of ['javascript:alert(1)', 'data:text/html,unsafe', '//evil.example', 'file:///test']) assert.equal(page.linkHref(url), undefined)
  assert.equal(page.linkHref('magnet:?xt=urn:btih:synthetic'), 'magnet:?xt=urn:btih:synthetic')
  assert.equal(page.safeMpUrl('/history'), '/history')
  for (const url of ['//evil.example', 'https://evil.example/history', '/\\evil.example', '/history\n']) assert.equal(page.safeMpUrl(url), undefined)
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

test('verify black box gives explicit outcomes for complete, failed, query error, queued and paused responses', async () => {
  for (const [data, expectedType] of [[{ confirmed: 1 }, 'success'], [{ failed: 1 }, 'error'], [{ query_error: 'HTTP 503' }, 'error'], [{ state: 'queued' }, 'info'], [{ paused: true }, 'warning']]) {
    const calls = []
    const page = component('Page', { post: async path => { calls.push(path); return { code: 0, data } }, get: async path => { calls.push(path); return { code: 0, data: [] } } })
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
  assert.ok([...timers.pending.values()][0].delay >= 40000)
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

test('UI version constants stay in step with the backend plugin version', () => {
  const page = readFileSync(new URL('src/components/Page.vue', ui), 'utf8')
  const config = readFileSync(new URL('src/components/Config.vue', ui), 'utf8')
  const manifest = JSON.parse(readFileSync(new URL('../../../package.v3.json', ui), 'utf8'))
  const version = String(manifest.Doc115Subscribe.version)
  const escaped = version.split('.').join('\.')
  assert.match(page, new RegExp("const UI_BUILD = '" + escaped + "'"))
  assert.match(config, new RegExp('前端 v' + escaped))
})
