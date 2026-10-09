// Synthetic UI contract tests. Run after `npm ci --ignore-scripts` in the plugin ui directory.
// No API, browser, download or remote storage is accessed.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'

const ui = new URL('../plugins.v3/doc115subscribe/ui/', import.meta.url)
const require = createRequire(new URL('package.json', ui))
const vue = require('vue')

function component(name, api) {
  const source = readFileSync(new URL(`src/components/${name}.vue`, ui), 'utf8')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .* from 'vue'\s*$/m, '')
  const emitted = []
  const helpers = { ...vue, onMounted() {}, onBeforeUnmount() {} }
  const names = name === 'Page'
    ? 'doSearch,searchPage,transfer,keyword,searchedKeyword,results,total,page,filterType,filterQuality,filterLink,busy,resultVersion,close,startQr,checkQr,qrSessionId,records,verifyRecords'
    : 'load,save,cfg,secrets,msg,msgType'
  const setup = new Function('helpers', 'suppliedProps', 'suppliedEmit', `
    const { computed, reactive, ref, watch, onMounted, onBeforeUnmount } = helpers;
    const defineProps = () => suppliedProps;
    const defineEmits = () => suppliedEmit;
    ${script}
    return { ${names} };
  `)
  return { ...setup(helpers, { api }, (...event) => emitted.push(event)), emitted }
}

const response = (id, version = 'version-1', total = 1) => ({ code: 0, data: {
  records: [{ record_id: id, title: id }], total, page: 1, page_size: 10, index_version: version,
} })
const deferred = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

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
  assert.deepEqual(calls[0], { keyword: 'locked keyword', media_type: 'tv', quality: '4k', link_kind: 'share', page: 3, page_size: 10 })
  assert.equal(page.total.value, 125)
  assert.equal(page.results.value.length, 1)
})

test('organize verification hits the verify endpoint then reloads records', async () => {
  const calls = []
  const page = component('Page', {
    post: async (path, payload) => {
      calls.push([path, payload])
      if (path.endsWith('/records_verify')) {
        return { code: 0, data: { checked: 2, confirmed: 1, partial: 0, failed: 0 } }
      }
      return { code: 0, data: [] }
    },
    get: async (path) => {
      calls.push([path, null])
      return { code: 0, data: [{ id: 'r1', status: 'organized', title: 'demo' }] }
    },
  })
  await page.verifyRecords()
  assert.equal(calls[0][0].endsWith('/records_verify'), true)
  assert.equal(calls.some(([p]) => String(p).endsWith('/records')), true)
  assert.equal(page.records.value.length, 1)
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
