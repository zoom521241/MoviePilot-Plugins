<template>
  <v-app>
    <v-main>
      <v-container>
        <PageComponent :api="apiStub" @action="noop" @close="noop" />
      </v-container>
    </v-main>
  </v-app>
</template>

<script setup>
import PageComponent from './components/Page.vue'

const apiStub = {
  get: async () => ({ code: 0, data: {} }),
  post: async () => ({ code: 0, data: {} }),
}
function noop() {}
</script>
