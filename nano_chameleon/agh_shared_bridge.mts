// Connect the official SDK to the verified, already-running local AGH daemon.
import { createInterface } from 'node:readline';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { randomUUID } from 'node:crypto';

const [profile, cwd, sdkRoot] = process.argv.slice(2);
if (!profile || !cwd || !sdkRoot) throw new Error('Profile, workspace and SDK source root are required');
let phase = 'loading the official SDK';
const bootstrapDeadline = setTimeout(() => {
  process.stderr.write(`AGH startup deadline reached while ${phase}\n`);
  process.exit(1);
}, 20000);
const load = (path: string) => import(pathToFileURL(resolve(sdkRoot, path)).href);
const {parseArgs} = await load('packages/cli/src/args.ts');
const {bootConnect, unixConnectTarget} = await load('packages/cli/src/boot/connect.ts');
const {resolveHome} = await load('packages/cli/src/boot/inputs.ts');
const {readDaemonDiscovery, resolveDaemonScope} = await load('packages/daemon/src/index.ts');
const deps = {env: process.env, home: resolveHome(process.env), cwd, agnesVersion: '0.0.0', log: () => {}};
phase = 'resolving the existing daemon scope';
const scope = await resolveDaemonScope({...deps, profile});
const discovery = await readDaemonDiscovery(scope);
if (!discovery) throw new Error('The existing AGH daemon is not available');
phase = 'connecting to the verified daemon';
const booted = await bootConnect(parseArgs(['--profile', profile, '--cwd', cwd,
  '--connect', unixConnectTarget(discovery.socketPath)]), deps);
clearTimeout(bootstrapDeadline);
const client = booted.client;
const sessions = new Map<string, any>();
const answers = new Map<string, (answer: any) => void>();
let permissionId = 0;
let serial = Promise.resolve();
const send = (message: unknown) => process.stdout.write(JSON.stringify(message) + '\n');
const events = new Set(['request/header', 'tool/call', 'tool/result', 'assistant/message', 'turn/end']);

async function handle(message: any) {
  const {method, params = {}, id} = message;
  try {
    let result: unknown;
    if (method === 'initialize') {
      await client.initialize();
      result = {protocolVersion: 1};
    } else if (method === 'session/new' || method === 'session/load') {
      if (method === 'session/new') await client.workspace.add(params.cwd);
      const session = method === 'session/load'
        ? await client.session.load(params.sessionId, {cwd: params.cwd})
        : await client.session.new({cwd: params.cwd, sessionKey: `nano-eval-${randomUUID()}`});
      sessions.set(session.id, session);
      session.onPermissionRequest(async (request: any, context: any) => {
        const requestId = `permission-${++permissionId}`;
        return await new Promise((resolve) => {
          const finish = (answer: any) => {
            answers.delete(requestId);
            context.signal.removeEventListener('abort', abort);
            const outcome = answer?.result?.outcome;
            resolve(outcome?.outcome === 'selected' ? {optionId: outcome.optionId} : {verdict: 'rejected'});
          };
          const abort = () => finish(null);
          answers.set(requestId, finish);
          context.signal.addEventListener('abort', abort, {once: true});
          send({jsonrpc: '2.0', id: requestId, method: 'session/request_permission', params: request});
        });
      });
      result = {sessionId: session.id};
    } else if (method === 'session/read_tool_detail') {
      const session = sessions.get(params.sessionId);
      if (!session) throw new Error('Unknown session');
      const detail = await session.readToolDetail(params.callSeq);
      const call = detail.call;
      result = {name: call.name, args: call.name === 'mcp_manage'
        ? {action: call.args?.action} : {}};
    } else if (method === '_agnes/v1/session.attach') {
      const session = sessions.get(params.sessionId);
      if (!session) throw new Error('Unknown session');
      await session.attach({filter: {acpUpdates: false}});
      void (async () => {
        for await (const event of session.events()) {
          if (events.has(event.type)) send({jsonrpc: '2.0', method: '_agnes/v1/session.event',
            params: {sessionId: session.id, event}});
        }
      })().catch(() => {});
      result = {lastSeq: session.lastServerSeq};
    } else if (method === 'session/prompt') {
      const session = sessions.get(params.sessionId);
      if (!session) throw new Error('Unknown session');
      result = await session.prompt(params.prompt, {titleLocale: 'zh-CN'});
    } else if (method === 'session/cancel') {
      await sessions.get(params.sessionId)?.cancel();
      result = {};
    } else {
      throw new Error('Unsupported bridge method');
    }
    if (id !== undefined) send({jsonrpc: '2.0', id, result});
  } catch (error: any) {
    if (id !== undefined) send({jsonrpc: '2.0', id, error: {
      code: -32603, message: String(error?.message ?? 'AGH operation failed').slice(0, 200)}});
  }
}

const input = createInterface({input: process.stdin, crlfDelay: Infinity});
input.on('line', (line) => {
  const message = JSON.parse(line);
  if (!message.method) answers.get(String(message.id))?.(message);
  else if (message.method === 'session/cancel') void handle(message);
  else serial = serial.then(() => handle(message));
});
input.on('close', async () => {
  for (const session of sessions.values()) await session.cancel().catch(() => {});
  await serial.catch(() => {});
  await booted.close();
});
