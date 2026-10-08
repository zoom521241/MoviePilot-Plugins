import { importShared } from './__federation_fn_import-C6HT7yLm.js';
import { R as IN_BROWSER, aJ as splitKeySequence, a7 as getActiveElement, aK as splitKeyCombination, z as isObject, aS as VClassIcon, aL as mergeDeep, aV as VSvgIcon, aW as createDefaults, aX as createDisplay, aY as createTheme, aZ as createLocale, a_ as createDate, a$ as createGoTo, a1 as defineComponent, b0 as DefaultsSymbol, b1 as DisplaySymbol, b2 as ThemeSymbol, b3 as IconSymbol, b4 as LocaleSymbol, b5 as DateOptionsSymbol, b6 as DateAdapterSymbol, b7 as GoToSymbol } from './hotkey-parsing-rEcAoAC3.js';
export { ai as useDate, b8 as useDefaults, Z as useDisplay, _ as useGoTo, aM as useLayout, T as useLocale, u as useRtl, L as useTheme } from './hotkey-parsing-rEcAoAC3.js';

const {onScopeDispose,toValue,watch} = await importShared('vue');
function useHotkey(keys, callback) {
  let options = arguments.length > 2 && arguments[2] !== undefined ? arguments[2] : {};
  if (!IN_BROWSER) return function () {};
  const {
    event = 'keydown',
    inputs = false,
    preventDefault = true,
    sequenceTimeout = 1000
  } = options;
  const isMac = navigator?.userAgent?.includes('Macintosh') ?? false;
  let timeout = 0;
  let keyGroups;
  let isSequence = false;
  let groupIndex = 0;
  function isInputFocused() {
    if (toValue(inputs)) return false;
    const activeElement = getActiveElement();
    return activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA' || activeElement.isContentEditable || activeElement.contentEditable === 'true');
  }
  function resetSequence() {
    groupIndex = 0;
    clearTimeout(timeout);
  }
  function handler(e) {
    const group = keyGroups[groupIndex];
    if (!group || isInputFocused()) return;
    if (!matchesKeyGroup(e, group, isMac)) {
      if (isSequence) resetSequence();
      return;
    }
    if (toValue(preventDefault)) e.preventDefault();
    if (!isSequence) {
      callback(e);
      return;
    }
    clearTimeout(timeout);
    groupIndex++;
    if (groupIndex === keyGroups.length) {
      callback(e);
      resetSequence();
      return;
    }
    timeout = window.setTimeout(resetSequence, toValue(sequenceTimeout));
  }
  function cleanup() {
    window.removeEventListener(toValue(event), handler);
    clearTimeout(timeout);
  }
  watch(() => toValue(keys), newKeys => {
    cleanup();
    if (newKeys) {
      const groups = splitKeySequence(newKeys.toLowerCase());
      isSequence = groups.length > 1;
      keyGroups = groups;
      resetSequence();
      window.addEventListener(toValue(event), handler);
    }
  }, {
    immediate: true
  });

  // Watch for changes in the event type to re-register the listener
  watch(() => toValue(event), (newEvent, oldEvent) => {
    if (oldEvent && keyGroups && keyGroups.length > 0) {
      window.removeEventListener(oldEvent, handler);
      window.addEventListener(newEvent, handler);
    }
  });
  onScopeDispose(cleanup, true);
  return cleanup;
}
function matchesKeyGroup(e, group, isMac) {
  const {
    modifiers,
    actualKey
  } = parseKeyGroup(group);
  const expectCtrl = modifiers.ctrl || !isMac && (modifiers.cmd || modifiers.meta);
  const expectMeta = isMac && (modifiers.cmd || modifiers.meta);
  return e.ctrlKey === expectCtrl && e.metaKey === expectMeta && e.shiftKey === modifiers.shift && e.altKey === modifiers.alt && e.key.toLowerCase() === actualKey?.toLowerCase();
}
function parseKeyGroup(group) {
  const MODIFIERS = ['ctrl', 'shift', 'alt', 'meta', 'cmd'];

  // Use the shared combination splitting logic
  const {
    keys: parts
  } = splitKeyCombination(group.toLowerCase());

  // If the combination is invalid, return empty result
  if (parts.length === 0) {
    return {
      modifiers: Object.fromEntries(MODIFIERS.map(m => [m, false])),
      actualKey: undefined
    };
  }
  const modifiers = Object.fromEntries(MODIFIERS.map(m => [m, false]));
  let actualKey;
  for (const part of parts) {
    if (MODIFIERS.includes(part)) {
      modifiers[part] = true;
    } else {
      actualKey = part;
    }
  }
  return {
    modifiers,
    actualKey
  };
}

// Utilities
const {computed} = await importShared('vue');
const defaultDelimiters = /[-!$%^&*()_+|~=`{}[\]:";'<>?,./\\ ]/;
const presets = {
  'credit-card': '#### - #### - #### - ####',
  date: '##/##/####',
  'date-time': '##/##/#### ##:##',
  'iso-date': '####-##-##',
  'iso-date-time': '####-##-## ##:##',
  phone: '(###) ### - ####',
  social: '###-##-####',
  time: '##:##',
  'time-with-seconds': '##:##:##'
};
const defaultTokens = {
  '#': {
    pattern: /[0-9]/
  },
  A: {
    pattern: /[A-Z]/i,
    convert: v => v.toUpperCase()
  },
  a: {
    pattern: /[a-z]/i,
    convert: v => v.toLowerCase()
  },
  N: {
    pattern: /[0-9A-Z]/i,
    convert: v => v.toUpperCase()
  },
  n: {
    pattern: /[0-9a-z]/i,
    convert: v => v.toLowerCase()
  },
  X: {
    pattern: defaultDelimiters
  }
};
function useMask(props) {
  const mask = computed(() => {
    if (typeof props.mask === 'string') {
      if (props.mask in presets) return presets[props.mask];
      return props.mask;
    }
    return props.mask?.mask ?? '';
  });
  const tokens = computed(() => {
    return {
      ...defaultTokens,
      ...(isObject(props.mask) ? props.mask.tokens : null)
    };
  });
  function isMask(char) {
    return char in tokens.value;
  }
  function maskValidates(mask, char) {
    if (char == null || !isMask(mask)) return false;
    const item = tokens.value[mask];
    if (item.pattern) return item.pattern.test(char);
    return item.test(char);
  }
  function convert(mask, char) {
    const item = tokens.value[mask];
    return item.convert ? item.convert(char) : char;
  }
  function maskText(text) {
    const trimmedText = text?.trim().replace(/\s+/g, ' ');
    if (trimmedText == null) return '';
    if (!mask.value.length || !trimmedText.length) return trimmedText;
    let textIndex = 0;
    let maskIndex = 0;
    let newText = '';
    while (maskIndex < mask.value.length) {
      const mchar = mask.value[maskIndex];
      const tchar = trimmedText[textIndex];

      // Escaped character in mask, the next mask character is inserted
      if (mchar === '\\') {
        newText += mask.value[maskIndex + 1];
        maskIndex += 2;
        continue;
      }
      if (!isMask(mchar)) {
        newText += mchar;
        if (tchar === mchar) {
          textIndex++;
        }
      } else if (maskValidates(mchar, tchar)) {
        newText += convert(mchar, tchar);
        textIndex++;
      } else {
        break;
      }
      maskIndex++;
    }
    return newText;
  }
  function unmaskText(text) {
    if (text == null) return null;
    if (!mask.value.length || !text.length) return text;
    let textIndex = 0;
    let maskIndex = 0;
    let newText = '';
    while (true) {
      const mchar = mask.value[maskIndex];
      const tchar = text[textIndex];
      if (tchar == null) break;
      if (mchar == null) {
        newText += tchar;
        textIndex++;
        continue;
      }

      // Escaped character in mask, skip the next input character
      if (mchar === '\\') {
        if (tchar === mask.value[maskIndex + 1]) {
          textIndex++;
        }
        maskIndex += 2;
        continue;
      }
      if (maskValidates(mchar, tchar)) {
        // masked char
        newText += tchar;
        textIndex++;
        maskIndex++;
        continue;
      } else if (mchar !== tchar) {
        // input doesn't match mask, skip forward until it does
        while (true) {
          const mchar = mask.value[maskIndex++];
          if (mchar == null || maskValidates(mchar, tchar)) break;
        }
        continue;
      }
      textIndex++;
      maskIndex++;
    }
    return newText;
  }
  function isValid(text) {
    if (!text) return false;
    return unmaskText(text) === unmaskText(maskText(text));
  }
  function isComplete(text) {
    if (!text) return false;
    const maskedText = maskText(text);
    return maskedText.length === mask.value.length && isValid(text);
  }
  return {
    isValid,
    isComplete,
    mask: maskText,
    unmask: unmaskText
  };
}

const {h} = await importShared('vue');


// Types

const aliases = {
  collapse: 'mdi-chevron-up',
  complete: 'mdi-check',
  cancel: 'mdi-close-circle',
  close: 'mdi-close',
  delete: 'mdi-close-circle',
  // delete (e.g. v-chip close)
  clear: 'mdi-close-circle',
  success: 'mdi-check-circle',
  info: 'mdi-information',
  warning: 'mdi-alert-circle',
  error: 'mdi-close-circle',
  prev: 'mdi-chevron-left',
  next: 'mdi-chevron-right',
  checkboxOn: 'mdi-checkbox-marked',
  checkboxOff: 'mdi-checkbox-blank-outline',
  checkboxIndeterminate: 'mdi-minus-box',
  delimiter: 'mdi-circle',
  // for carousel
  sortAsc: 'mdi-arrow-up',
  sortDesc: 'mdi-arrow-down',
  expand: 'mdi-chevron-down',
  menu: 'mdi-menu',
  subgroup: 'mdi-menu-down',
  dropdown: 'mdi-menu-down',
  radioOn: 'mdi-radiobox-marked',
  radioOff: 'mdi-radiobox-blank',
  edit: 'mdi-pencil',
  ratingEmpty: 'mdi-star-outline',
  ratingFull: 'mdi-star',
  ratingHalf: 'mdi-star-half-full',
  loading: 'mdi-cached',
  first: 'mdi-page-first',
  last: 'mdi-page-last',
  unfold: 'mdi-unfold-more-horizontal',
  file: 'mdi-paperclip',
  plus: 'mdi-plus',
  minus: 'mdi-minus',
  calendar: 'mdi-calendar',
  treeviewCollapse: 'mdi-menu-down',
  treeviewExpand: 'mdi-menu-right',
  tableGroupCollapse: 'mdi-chevron-down',
  tableGroupExpand: 'mdi-chevron-right',
  eyeDropper: 'mdi-eyedropper',
  upload: 'mdi-cloud-upload',
  color: 'mdi-palette',
  command: 'mdi-apple-keyboard-command',
  ctrl: 'mdi-apple-keyboard-control',
  space: 'mdi-keyboard-space',
  shift: 'mdi-apple-keyboard-shift',
  alt: 'mdi-apple-keyboard-option',
  enter: 'mdi-keyboard-return',
  arrowup: 'mdi-arrow-up',
  arrowdown: 'mdi-arrow-down',
  arrowleft: 'mdi-arrow-left',
  arrowright: 'mdi-arrow-right',
  backspace: 'mdi-backspace',
  play: 'mdi-play',
  pause: 'mdi-pause',
  fullscreen: 'mdi-fullscreen',
  fullscreenExit: 'mdi-fullscreen-exit',
  volumeHigh: 'mdi-volume-high',
  volumeMedium: 'mdi-volume-medium',
  volumeLow: 'mdi-volume-low',
  volumeOff: 'mdi-volume-variant-off',
  search: 'mdi-magnify'
};
const mdi = {
  // Not using mergeProps here, functional components merge props by default (?)
  component: props => h(VClassIcon, {
    ...props,
    class: 'mdi'
  })
};

// Composables
function genDefaults() {
  return {
    svg: {
      component: VSvgIcon
    },
    class: {
      component: VClassIcon
    }
  };
}
function createIcons(options) {
  const sets = genDefaults();
  const defaultSet = options?.defaultSet ?? 'mdi';
  if (defaultSet === 'mdi' && !sets.mdi) {
    sets.mdi = mdi;
  }
  return mergeDeep({
    defaultSet,
    sets,
    aliases: {
      ...aliases,
      /* eslint-disable max-len */
      vuetify: ['M8.2241 14.2009L12 21L22 3H14.4459L8.2241 14.2009Z', ['M7.26303 12.4733L7.00113 12L2 3H12.5261C12.5261 3 12.5261 3 12.5261 3L7.26303 12.4733Z', 0.6]],
      'vuetify-outline': 'svg:M7.26 12.47 12.53 3H2L7.26 12.47ZM14.45 3 8.22 14.2 12 21 22 3H14.45ZM18.6 5 12 16.88 10.51 14.2 15.62 5ZM7.26 8.35 5.4 5H9.13L7.26 8.35Z',
      'vuetify-play': ['m6.376 13.184-4.11-7.192C1.505 4.66 2.467 3 4.003 3h8.532l-.953 1.576-.006.01-.396.677c-.429.732-.214 1.507.194 2.015.404.503 1.092.878 1.869.806a3.72 3.72 0 0 1 1.005.022c.276.053.434.143.523.237.138.146.38.635-.25 2.09-.893 1.63-1.553 1.722-1.847 1.677-.213-.033-.468-.158-.756-.406a4.95 4.95 0 0 1-.8-.927c-.39-.564-1.04-.84-1.66-.846-.625-.006-1.316.27-1.693.921l-.478.826-.911 1.506Z', ['M9.093 11.552c.046-.079.144-.15.32-.148a.53.53 0 0 1 .43.207c.285.414.636.847 1.046 1.2.405.35.914.662 1.516.754 1.334.205 2.502-.698 3.48-2.495l.014-.028.013-.03c.687-1.574.774-2.852-.005-3.675-.37-.391-.861-.586-1.333-.676a5.243 5.243 0 0 0-1.447-.044c-.173.016-.393-.073-.54-.257-.145-.18-.127-.316-.082-.392l.393-.672L14.287 3h5.71c1.536 0 2.499 1.659 1.737 2.992l-7.997 13.996c-.768 1.344-2.706 1.344-3.473 0l-3.037-5.314 1.377-2.278.004-.006.004-.007.481-.831Z', 0.6]]
      /* eslint-enable max-len */
    }
  }, options);
}

const {effectScope,nextTick,reactive} = await importShared('vue');
function createVuetify() {
  let vuetify = arguments.length > 0 && arguments[0] !== void 0 ? arguments[0] : {};
  const {
    blueprint,
    ...rest
  } = vuetify;
  const options = mergeDeep(blueprint, rest);
  const {
    aliases = {},
    components = {},
    directives = {}
  } = options;
  const scope = effectScope();
  return scope.run(() => {
    const defaults = createDefaults(options.defaults);
    const display = createDisplay(options.display, options.ssr);
    const theme = createTheme(options.theme);
    const icons = createIcons(options.icons);
    const locale = createLocale(options.locale);
    const date = createDate(options.date, locale);
    const goTo = createGoTo(options.goTo, locale);
    function install(app) {
      for (const key in directives) {
        app.directive(key, directives[key]);
      }
      for (const key in components) {
        app.component(key, components[key]);
      }
      for (const key in aliases) {
        app.component(key, defineComponent({
          ...aliases[key],
          name: key,
          aliasName: aliases[key].name
        }));
      }
      const appScope = effectScope();
      appScope.run(() => {
        theme.install(app);
      });
      app.onUnmount(() => appScope.stop());
      app.provide(DefaultsSymbol, defaults);
      app.provide(DisplaySymbol, display);
      app.provide(ThemeSymbol, theme);
      app.provide(IconSymbol, icons);
      app.provide(LocaleSymbol, locale);
      app.provide(DateOptionsSymbol, date.options);
      app.provide(DateAdapterSymbol, date.instance);
      app.provide(GoToSymbol, goTo);
      if (IN_BROWSER && options.ssr) {
        if (app.$nuxt) {
          app.$nuxt.hook("app:suspense:resolve", () => {
            display.update();
          });
        } else {
          const {
            mount
          } = app;
          app.mount = function() {
            const vm = mount(...arguments);
            nextTick(() => display.update());
            app.mount = mount;
            return vm;
          };
        }
      }
      {
        app.mixin({
          computed: {
            $vuetify() {
              return reactive({
                defaults: inject.call(this, DefaultsSymbol),
                display: inject.call(this, DisplaySymbol),
                theme: inject.call(this, ThemeSymbol),
                icons: inject.call(this, IconSymbol),
                locale: inject.call(this, LocaleSymbol),
                date: inject.call(this, DateAdapterSymbol)
              });
            }
          }
        });
      }
    }
    function unmount() {
      scope.stop();
    }
    return {
      install,
      unmount,
      defaults,
      display,
      theme,
      icons,
      locale,
      date,
      goTo
    };
  });
}
const version = "3.13.6";
createVuetify.version = version;
function inject(key) {
  const vm = this.$;
  const provides = vm.parent?.provides ?? vm.vnode.appContext?.provides;
  if (provides && key in provides) {
    return provides[key];
  }
}

export { createVuetify, useHotkey, useMask, version };
