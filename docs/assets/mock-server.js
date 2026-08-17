  /* The mock server, installed before htmx loads.
   *
   * htmx sends real XMLHttpRequests. This shim answers the ones addressed to
   * /demo/* and forwards everything else to the browser's own XHR, so the
   * demos below are genuine htmx round trips — real headers, real latency, a
   * real swap — with the FastAPI side played by 60 lines of JavaScript. */
  (() => {
    const Native = window.XMLHttpRequest;
    const routes = [];
    const listeners = [];

    window.__tMock = {
      route: (method, pattern, handler) => routes.push({ method, pattern, handler }),
      onExchange: (fn) => listeners.push(fn),
      latency: 260,
    };

    class MockXHR {
      constructor() {
        this.headers = {};
        this.readyState = 0;
        this.status = 0;
        this.responseText = "";
        // htmx attaches progress listeners to both the request and its upload,
        // so the upload has to be an event target even though a mock never
        // reports progress.
        this.upload = { addEventListener() {}, removeEventListener() {} };
        this._listeners = {};
      }

      open(method, url) {
        this.method = method.toUpperCase();
        this.url = url;
        const [path, query] = url.split("?");
        this.path = path;
        this.query = new URLSearchParams(query || "");
        this.match = routes.find((r) => r.method === this.method && r.pattern.test(this.path));
        if (!this.match) {
          this.native = new Native();
          this.native.open(method, url);
        }
      }

      setRequestHeader(name, value) {
        this.headers[name] = value;
        if (this.native) this.native.setRequestHeader(name, value);
      }

      getAllResponseHeaders() { return "content-type: text/html\r\n"; }
      getResponseHeader(name) { return name.toLowerCase() === "content-type" ? "text/html" : null; }
      overrideMimeType(type) { if (this.native) this.native.overrideMimeType(type); }
      addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); }
      removeEventListener(type, fn) {
        this._listeners[type] = (this._listeners[type] || []).filter((f) => f !== fn);
      }
      abort() { this.aborted = true; }

      _fire(type) {
        const event = { type, target: this, lengthComputable: false };
        (this._listeners[type] || []).forEach((fn) => fn.call(this, event));
        const inline = this[`on${type}`];
        if (typeof inline === "function") inline.call(this, event);
      }

      send(body) {
        if (this.native) {
          Object.keys(this._listeners).forEach((type) =>
            this._listeners[type].forEach((fn) => this.native.addEventListener(type, fn)));
          return this.native.send(body);
        }

        const request = {
          method: this.method,
          path: this.path,
          query: this.query,
          body: new URLSearchParams(typeof body === "string" ? body : ""),
          headers: this.headers,
        };

        setTimeout(() => {
          if (this.aborted) return;
          const { status = 200, text = "" } = this.match.handler(request, this.path.match(this.match.pattern)) || {};
          this.status = status;
          this.statusText = status === 200 ? "OK" : "";
          this.responseText = text;
          this.response = text;
          // Absolute, because htmx compares it against the document's origin
          // before it will trust a response.
          this.responseURL = new URL(this.url, document.baseURI).href;
          this.readyState = 4;
          listeners.forEach((fn) => fn(request, { status, text }));
          this._fire("load");
          this._fire("loadend");
        }, window.__tMock.latency);
      }
    }

    window.XMLHttpRequest = MockXHR;
  })();
