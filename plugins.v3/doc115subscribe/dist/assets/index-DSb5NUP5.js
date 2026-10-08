import { importShared } from './__federation_fn_import-SdO2Fg_T.js';
import _sfc_main$1 from './__federation_expose_Page-Do5cpI9A.js';

const {createVNode:_createVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');


const _sfc_main = {
  __name: 'App',
  setup(__props) {

const apiStub = {
  get: async () => ({ code: 0, data: {} }),
  post: async () => ({ code: 0, data: {} }),
};
function noop() {}

return (_ctx, _cache) => {
  const _component_v_container = _resolveComponent("v-container");
  const _component_v_main = _resolveComponent("v-main");
  const _component_v_app = _resolveComponent("v-app");

  return (_openBlock(), _createBlock(_component_v_app, null, {
    default: _withCtx(() => [
      _createVNode(_component_v_main, null, {
        default: _withCtx(() => [
          _createVNode(_component_v_container, null, {
            default: _withCtx(() => [
              _createVNode(_sfc_main$1, {
                api: apiStub,
                onAction: noop,
                onClose: noop
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _: 1
  }))
}
}

};

const {createApp} = await importShared('vue');
{
  createApp(_sfc_main).mount("#app");
}
