#!/usr/bin/env node
import { spawnSync } from 'node:child_process';

const images = [
  ['images.r9.all-hands.dev/proxy/openhands/bitnamilegacy/postgresql:latest', 'bitnamilegacy/postgresql:latest'],
  ['images.r9.all-hands.dev/proxy/openhands/busybox', 'busybox'],
  ['images.r9.all-hands.dev/proxy/openhands/docker.io/bitnamilegacy/keycloak:26.3.0-debian-12-r0', 'bitnamilegacy/keycloak:26.3.0-debian-12-r0'],
  ['images.r9.all-hands.dev/proxy/openhands/docker.io/bitnamilegacy/postgresql:16.4.0-debian-12-r14', 'bitnamilegacy/postgresql:16.4.0-debian-12-r14'],
  ['images.r9.all-hands.dev/proxy/openhands/docker.io/bitnamilegacy/redis:7.4.1-debian-12-r2', 'bitnamilegacy/redis:7.4.1-debian-12-r2'],
  ['images.r9.all-hands.dev/proxy/openhands/ghcr.io/berriai/litellm-database:main-v1.80.8-nightly', 'berriai/litellm-database:main-v1.80.8-nightly'],
  ['images.r9.all-hands.dev/proxy/openhands/ghcr.io/openhands/enterprise-server:sha-0105238', 'openhands/enterprise-server:sha-0105238'],
  ['images.r9.all-hands.dev/proxy/openhands/ghcr.io/openhands/runtime-api:sha-fd990c4', 'openhands/runtime-api:sha-fd990c4'],
  ['images.r9.all-hands.dev/proxy/openhands/quay.io/jetstack/cert-manager-cainjector:v1.20.2', 'jetstack/cert-manager-cainjector:v1.20.2'],
  ['images.r9.all-hands.dev/proxy/openhands/quay.io/jetstack/cert-manager-controller:v1.20.2', 'jetstack/cert-manager-controller:v1.20.2'],
  ['images.r9.all-hands.dev/proxy/openhands/quay.io/jetstack/cert-manager-startupapicheck:v1.20.2', 'jetstack/cert-manager-startupapicheck:v1.20.2'],
  ['images.r9.all-hands.dev/proxy/openhands/quay.io/jetstack/cert-manager-webhook:v1.20.2', 'jetstack/cert-manager-webhook:v1.20.2'],
  ['images.r9.all-hands.dev/proxy/openhands/quay.io/jetstack/trust-manager:v0.22.1', 'jetstack/trust-manager:v0.22.1'],
  ['images.r9.all-hands.dev/proxy/openhands/quay.io/jetstack/trust-pkg-debian-bookworm:20230311-deb12u1.6', 'jetstack/trust-pkg-debian-bookworm:20230311-deb12u1.6'],
];

function argValue(name) {
  const index = process.argv.indexOf(name);
  if (index < 0) return undefined;
  return process.argv[index + 1];
}

function usage() {
  console.log(`Usage:
  pnpm openhands:mirror -- --registry registry.example.com [--apply]

Default mode is dry-run and prints the docker commands. Use --apply only on a trusted host that is already logged in to the private registry.
`);
}

const registryInput = argValue('--registry') || process.env.OPENHANDS_PRIVATE_REGISTRY || '';
const apply = process.argv.includes('--apply');
const registry = registryInput.trim().replace(/\/+$/, '');

if (!registry || process.argv.includes('--help')) {
  usage();
  process.exit(registry ? 0 : 1);
}

function targetFor(relative) {
  return `${registry}/openhands/${relative}`;
}

function run(command, args) {
  const rendered = [command, ...args].join(' ');
  if (!apply) {
    console.log(rendered);
    return;
  }
  const result = spawnSync(command, args, { stdio: 'inherit' });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

console.log(`# OpenHands Enterprise image mirror ${apply ? 'apply' : 'dry-run'}`);
console.log(`# Target prefix: ${registry}/openhands`);
console.log('# This helper never handles registry passwords. Run docker login separately.');

for (const [source] of images) run('docker', ['pull', source]);
for (const [source, relative] of images) run('docker', ['tag', source, targetFor(relative)]);
for (const [, relative] of images) run('docker', ['push', targetFor(relative)]);
