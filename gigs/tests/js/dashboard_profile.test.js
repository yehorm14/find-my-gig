// Regression tests for the profile page pending-media state in dashboard.js.
// Run with: node gigs/tests/js/dashboard_profile.test.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const jsDir = path.join(__dirname, '..', '..', '..', 'static', 'find_my_gig', 'js');
const { createMediaState } = require(path.join(jsDir, 'media_state.js'));

// ---- minimal DOM stub ----
class El {
    constructor(tag, id) {
        this.tagName = tag; this.id = id || ''; this.children = []; this.parentElement = null;
        this.dataset = {}; this.value = ''; this.files = []; this.disabled = false; this.style = {};
        this.listeners = {}; this.classes = new Set(); this.textContent = '';
        const self = this;
        this.classList = { add: c => self.classes.add(c), contains: c => self.classes.has(c) };
    }
    set className(v) { this.classes = new Set(String(v).split(/\s+/).filter(Boolean)); }
    get className() { return [...this.classes].join(' '); }
    appendChild(c) { c.parentElement = this; this.children.push(c); return c; }
    remove() { if (this.parentElement) { this.parentElement.children = this.parentElement.children.filter(c => c !== this); this.parentElement = null; } }
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
    all() { return this.children.flatMap(c => [c, ...c.all()]); }
    querySelector(sel) { return this.all().find(e => match(e, sel)) || null; }
}
function match(e, sel) {
    let m = sel.match(/^\.([\w-]+)\[data-media-id="(.+)"\]$/);
    if (m) return e.classes.has(m[1]) && e.dataset.mediaId === m[2];
    m = sel.match(/^\.([\w-]+)$/);
    return m ? e.classes.has(m[1]) : false;
}

function setup(fetchImpl) {
    const body = new El('body');
    const els = {};
    ['update-profile-btn', 'profile-username', 'about', 'profile-about', 'add-media-btn', 'media-link-input',
     'media-links-list', 'status-message'].forEach(id => { els[id] = body.appendChild(new El('x', id)); });
    els['profile-username'].value = 'user';
    const docListeners = {};
    const document = {
        addEventListener: (t, fn) => { docListeners[t] = fn; },
        getElementById: id => els[id] || null,
        createElement: tag => new El(tag),
        querySelector: sel => body.querySelector(sel),
        querySelectorAll: () => [],
        cookie: ''
    };
    const ctx = vm.createContext({
        document, fetch: fetchImpl, console, setTimeout: () => 0, URL, JSON, Promise,
        confirm: () => true, window: { location: {} }, FormData: class {}
    });
    ctx.createMediaState = createMediaState;
    vm.runInContext(fs.readFileSync(path.join(jsDir, 'utils.js'), 'utf8').split('// FORCE FRESH')[0], ctx);
    vm.runInContext(fs.readFileSync(path.join(jsDir, 'dashboard.js'), 'utf8'), ctx);
    docListeners.DOMContentLoaded();
    const list = els['media-links-list'];
    const api = {
        els, list,
        add(url) { els['media-link-input'].value = url; els['add-media-btn'].listeners.click[0]({ preventDefault() {}, stopPropagation() {} }); },
        buttons() { return list.all().filter(e => e.classes.has('delete-media-btn')); },
        del(idx) { const b = api.buttons()[idx]; list.listeners.click[0]({ target: b }); },
        save() { els['update-profile-btn'].listeners.click[0](); return new Promise(r => setImmediate(() => setImmediate(r))); },
        status() { return els['status-message'].textContent; }
    };
    return api;
}

function res(body, { ok = true, status = 200, type = 'application/json', redirected = false } = {}) {
    return Promise.resolve({
        ok, status, redirected, headers: { get: () => type },
        json: () => typeof body === 'string' ? Promise.reject(new SyntaxError('bad json')) : Promise.resolve(body)
    });
}

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('state: add A/B/C, delete A and B leaves only C pending', () => {
    const s = createMediaState();
    const a = s.addPending('A'), b = s.addPending('B'), c = s.addPending('C');
    s.remove(a); s.remove(b);
    assert.deepStrictEqual(s.snapshot().links.map(l => l.url), ['C']);
    assert.ok(c);
});

test('state: ids are never reused after delete then add', () => {
    const s = createMediaState();
    const a = s.addPending('A'); s.addPending('B');
    s.remove(a);
    const d = s.addPending('D');
    const ids = s.snapshot().links.map(l => l.id);
    assert.strictEqual(new Set(ids).size, ids.length);
    assert.ok(!ids.slice(0, 1).includes(d));
});

test('state: commit keeps edits queued while the save was in flight', () => {
    const s = createMediaState();
    s.addPending('A'); s.remove('7');
    const snap = s.snapshot();
    s.addPending('B'); s.remove('8');
    s.commit(snap, [{ id: 1, url: 'A' }]);
    const left = s.snapshot();
    assert.deepStrictEqual(left.links.map(l => l.url), ['B']);
    assert.deepStrictEqual(left.deletes, ['8']);
});

test('ui: saving twice does not resend a saved link', async () => {
    const bodies = [];
    const ui = setup((url, cfg) => { bodies.push(JSON.parse(cfg.body)); return res({ success: true, media_links: bodies.length === 1 ? [{ id: 42, url: 'https://a.com' }] : [] }); });
    ui.add('https://a.com');
    await ui.save();
    await ui.save();
    assert.deepStrictEqual(bodies[0].media_links, ['https://a.com']);
    assert.deepStrictEqual(bodies[1].media_links, []);
    assert.strictEqual(ui.buttons()[0].dataset.mediaId, '42');
});

test('ui: deleting a submitted link during a save queues deletion of its persisted id', async () => {
    const bodies = [];
    let finishSave;
    const firstSave = new Promise(resolve => { finishSave = resolve; });
    const ui = setup((url, cfg) => {
        bodies.push(JSON.parse(cfg.body));
        return bodies.length === 1
            ? firstSave
            : res({ success: true, media_links: [] });
    });
    ui.add('https://a.com');
    const saving = ui.save();
    ui.del(0);
    finishSave(res({ success: true, media_links: [{ id: 42, url: 'https://a.com' }] }));
    await saving;
    assert.strictEqual(ui.buttons().length, 0);
    assert.match(ui.status(), /remaining link changes/);
    await ui.save();
    assert.deepStrictEqual(bodies[1].delete_media, ['42']);
});

test('ui: pages without the profile script still wire dashboard handlers', () => {
    let initialize;
    const withdrawApplication = new El('button');
    const document = {
        addEventListener: (type, callback) => { initialize = callback; },
        getElementById: () => null,
        querySelectorAll: selector => selector === '.withdraw-application-btn' ? [withdrawApplication] : []
    };
    vm.runInNewContext(fs.readFileSync(path.join(jsDir, 'dashboard.js'), 'utf8'), { document });
    initialize();
    assert.strictEqual(withdrawApplication.listeners.click?.length, 1);
});

test('ui: saved link can then be deleted by its persisted id', async () => {
    const bodies = [];
    const ui = setup((url, cfg) => { bodies.push(JSON.parse(cfg.body)); return res({ success: true, media_links: [{ id: 42, url: 'https://a.com' }] }); });
    ui.add('https://a.com');
    await ui.save();
    ui.del(0);
    await ui.save();
    assert.deepStrictEqual(bodies[1].delete_media, ['42']);
});

test('ui: add A/B/C, delete A and B, only C is sent', async () => {
    const bodies = [];
    const ui = setup((url, cfg) => { bodies.push(JSON.parse(cfg.body)); return res({ success: true, media_links: [{ id: 1, url: 'https://c.com' }] }); });
    ['https://a.com', 'https://b.com', 'https://c.com'].forEach(u => ui.add(u));
    ui.del(0); ui.del(0);
    await ui.save();
    assert.deepStrictEqual(bodies[0].media_links, ['https://c.com']);
});

const failures = {
    'offline': () => Promise.reject(new TypeError('Failed to fetch')),
    'HTML error page': () => res('<html>500</html>', { ok: false, status: 500, type: 'text/html' }),
    'expired session redirect to login': () => res('<html>login</html>', { redirected: true, type: 'text/html' }),
    'non-2xx without JSON body': () => res('x', { ok: false, status: 502 }),
};
Object.entries(failures).forEach(([name, impl]) => {
    test(`ui: ${name} shows failure and preserves edits for retry`, async () => {
        let calls = 0;
        const bodies = [];
        const ui = setup((url, cfg) => { bodies.push(JSON.parse(cfg.body)); calls++; return calls === 1 ? impl() : res({ success: true, media_links: [{ id: 5, url: 'https://a.com' }] }); });
        ui.add('https://a.com'); ui.del(0); ui.add('https://a.com');
        await ui.save();
        assert.ok(/could not save/i.test(ui.status()), ui.status());
        await ui.save();
        assert.deepStrictEqual(bodies[1], bodies[0]);
        assert.strictEqual(ui.els['update-profile-btn'].disabled, false);
    });
});

test('ui: non-2xx JSON error (#18 status codes) is shown and preserves edits', async () => {
    let calls = 0;
    const bodies = [];
    const ui = setup((url, cfg) => { bodies.push(JSON.parse(cfg.body)); calls++; return calls === 1 ? res({ success: false, error: 'invalid', errors: { about: ['Required.'] } }, { ok: false, status: 400 }) : res({ success: true, media_links: [{ id: 5, url: 'https://a.com' }] }); });
    ui.add('https://a.com');
    await ui.save();
    assert.ok(ui.status().includes('about: Required.'), ui.status());
    await ui.save();
    assert.deepStrictEqual(bodies[1].media_links, ['https://a.com']);
});

test('ui: non-2xx JSON without success flag is still a failure', async () => {
    let calls = 0;
    const ui = setup(() => { calls++; return calls === 1 ? res({ error: 'x' }, { ok: false, status: 500 }) : res({ success: true, media_links: [] }); });
    ui.add('https://a.com');
    await ui.save();
    assert.ok(/something went wrong/i.test(ui.status()), ui.status());
});

(async () => {
    let failed = 0;
    for (const [name, fn] of tests) {
        try { await fn(); console.log('ok   - ' + name); }
        catch (e) { failed++; console.log('FAIL - ' + name + '\n  ' + (e.stack || e)); }
    }
    console.log(`${tests.length - failed}/${tests.length} passed`);
    process.exit(failed ? 1 : 0);
})();
