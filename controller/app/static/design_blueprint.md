# VPS UFW Firewall Manager: Visual Design & HTML Structure Blueprint

This blueprint outlines the visual design language, CSS variables, HTML structures, and HTMX implementation plan for the **VPS UFW Firewall Manager** (a web interface to control UFW firewalls across multiple VPS nodes).

---

## 1. Design System

To match the premium developer-focused nature of the tool, the design is a **sleek dark mode** interface leveraging a high-contrast palette of neon purples/blues, glassmorphism, glowing borders, and smooth micro-animations.

### CSS Custom Properties (Variables)
Place these in the root CSS file (e.g., `style.css` or inside a `<style>` block):

```css
:root {
  /* Color Palette */
  --bg-primary: #0a0814;      /* Deep midnight background */
  --bg-secondary: #120e25;    /* Card & container dark base */
  --bg-glass: rgba(18, 14, 37, 0.7); /* Translucent glass overlay */
  --border-glass: rgba(255, 255, 255, 0.08);
  --border-glow: rgba(139, 92, 246, 0.2); /* Soft violet glow */

  /* Neon Accents */
  --accent-purple: #8b5cf6;   /* Vivid Purple */
  --accent-blue: #3b82f6;     /* Bright Blue */
  --accent-teal: #14b8a6;     /* Teal for success/online */
  --accent-pink: #ec4899;     /* Pink for alerts/active rule */
  --accent-red: #ef4444;      /* Red for critical/delete/close */

  /* Text Colors */
  --text-primary: #f3f4f6;    /* Off-white */
  --text-secondary: #9ca3af;  /* Muted gray */
  --text-muted: #6b7280;      /* Darker gray for metadata */

  /* Fonts */
  --font-sans: 'Outfit', 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

  /* Shadows */
  --shadow-glow-purple: 0 0 20px rgba(139, 92, 246, 0.15);
  --shadow-glow-teal: 0 0 15px rgba(20, 184, 166, 0.2);
  --shadow-glow-red: 0 0 15px rgba(239, 68, 68, 0.25);
  --shadow-card: 0 10px 30px -10px rgba(0, 0, 0, 0.7);

  /* Layout */
  --radius-lg: 16px;
  --radius-md: 12px;
  --radius-sm: 8px;
  --transition-smooth: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
```

### Typography & Fonts
- **Headings & Callouts**: `'Outfit'` (geometric, modern, clean, tech-forward).
- **Body & Controls**: `'Inter'` (highly legible, clean).
- **Port numbers & IPs**: `'JetBrains Mono'` or `'Fira Code'` (monospaced to ensure layout stability and readability of network configurations).

### Card Styling & Glassmorphism
Premium components use background blur (`backdrop-filter`) and thin, semi-transparent borders with subtle box-shadow glows:

```css
.glass-card {
  background: var(--bg-glass);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--border-glass);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  transition: var(--transition-smooth);
}

.glass-card:hover {
  border-color: rgba(139, 92, 246, 0.35);
  box-shadow: var(--shadow-card), var(--shadow-glow-purple);
  transform: translateY(-4px); /* Interactive lift */
}
```

### Micro-Animations
```css
/* Status Pulse for active agents / online nodes */
@keyframes pulse-glow {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(20, 184, 166, 0.7);
  }
  50% {
    transform: scale(1.1);
    box-shadow: 0 0 10px 4px rgba(20, 184, 166, 0.3);
  }
}

.status-pulse-online {
  width: 8px;
  height: 8px;
  background-color: var(--accent-teal);
  border-radius: 50%;
  animation: pulse-glow 2s infinite;
}

@keyframes pulse-offline {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7);
  }
  50% {
    transform: scale(1.1);
    box-shadow: 0 0 10px 4px rgba(239, 68, 68, 0.3);
  }
}

.status-pulse-offline {
  width: 8px;
  height: 8px;
  background-color: var(--accent-red);
  border-radius: 50%;
  animation: pulse-offline 2s infinite;
}

/* Spinner for HTMX indicator */
.htmx-indicator {
  opacity: 0;
  transition: opacity 150ms ease-in;
}
.htmx-request .htmx-indicator {
  opacity: 1;
}
.htmx-request.htmx-indicator {
  opacity: 1;
}
```

---

## 2. Dashboard Page

The main entry point lists all VPS nodes in a responsive grid. Each node card displays real-time connection telemetry, active ports, operating system tags, and acts as a gateway to the detail view.

### HTML Structure Blueprint (Dashboard)

```html
<!-- Base Page Structure (dashboard.html) -->
<div class="container mx-auto px-4 py-8">
  <!-- Header Section -->
  <header class="flex justify-between items-center mb-10">
    <div>
      <h1 class="text-3xl font-extrabold tracking-tight text-white font-outfit">
        VPS UFW Firewall Manager
      </h1>
      <p class="text-sm text-gray-400 mt-1">
        Centralized monitoring and rule deployment for edge relays
      </p>
    </div>
    
    <!-- Unified Sync Action -->
    <button 
      class="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white font-medium py-2 px-4 rounded-lg transition-all"
      hx-post="/api/nodes/sync-all"
      hx-target="#nodes-grid"
      hx-indicator="#global-spinner"
    >
      <svg class="w-4 h-4 animate-spin htmx-indicator" id="global-spinner" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
      Refresh All Nodes
    </button>
  </header>

  <!-- Nodes Grid -->
  <div 
    id="nodes-grid" 
    class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
    hx-get="/api/nodes" 
    hx-trigger="load" 
    hx-swap="innerHTML"
  >
    <!-- Placeholder loading skeleton (Replaced by HTMX load) -->
    <div class="animate-pulse bg-gray-900 border border-gray-800 rounded-2xl h-56 p-6">
      <div class="h-4 bg-gray-800 rounded w-1/3 mb-4"></div>
      <div class="h-8 bg-gray-800 rounded mb-4"></div>
      <div class="h-4 bg-gray-800 rounded w-5/6"></div>
    </div>
  </div>
</div>
```

### Individual Node Card Partial Structure (`/api/nodes` returns a list of these)

```html
<!-- Node Card Partial -->
<div class="glass-card p-6 flex flex-col justify-between h-full group cursor-pointer"
     hx-get="/node/hk-relay-01" 
     hx-target="body" 
     hx-push-url="true">
  <div>
    <!-- Card Header: Node Hostname & Active Status Pulse -->
    <div class="flex justify-between items-start mb-4">
      <div>
        <h3 class="text-xl font-bold text-white group-hover:text-purple-400 transition-colors font-outfit">
          hk-relay-01
        </h3>
        <span class="text-xs font-mono text-gray-500">47.242.88.190</span>
      </div>
      <!-- Status Badge -->
      <div class="flex items-center gap-2 px-2.5 py-1 rounded-full bg-teal-950/40 border border-teal-500/25">
        <span class="status-pulse-online"></span>
        <span class="text-[10px] font-bold tracking-wider text-teal-400 uppercase">ONLINE</span>
      </div>
    </div>

    <!-- Metadata & Connectivity -->
    <div class="space-y-2 mb-6">
      <div class="flex justify-between text-xs">
        <span class="text-gray-400">OS/Kernel:</span>
        <span class="text-gray-200 font-medium font-mono">Ubuntu 22.04 / 5.15.0</span>
      </div>
      <div class="flex justify-between text-xs">
        <span class="text-gray-400">SSH Connectivity:</span>
        <span class="text-teal-400 font-medium flex items-center gap-1">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path>
          </svg>
          Success (22ms)
        </span>
      </div>
    </div>
  </div>

  <!-- Footer Tag-list of active ports -->
  <div>
    <div class="border-t border-gray-800/80 pt-4">
      <div class="text-[10px] text-gray-400 uppercase font-bold tracking-wider mb-2">
        Active Ports (UFW Enabled)
      </div>
      <div class="flex flex-wrap gap-1.5">
        <span class="px-2 py-0.5 text-xs font-mono rounded bg-purple-900/40 border border-purple-500/30 text-purple-300">
          22/tcp
        </span>
        <span class="px-2 py-0.5 text-xs font-mono rounded bg-blue-900/40 border border-blue-500/30 text-blue-300">
          28261/udp
        </span>
        <span class="px-2 py-0.5 text-xs font-mono rounded bg-pink-900/40 border border-pink-500/30 text-pink-300">
          8388/tcp+udp
        </span>
        <span class="px-2 py-0.5 text-xs text-gray-400 font-mono bg-gray-800/50 rounded">
          +3 more
        </span>
      </div>
    </div>
  </div>
</div>
```

---

## 3. Node Firewall Detail Page

Selecting a node loads the Node detail view, containing full state diagnostics, network telemetry, and an interactive UFW configuration layout organized into a **Port Cards Grid**.

### Detail Page Header
```html
<div class="container mx-auto px-4 py-8">
  <!-- Dynamic Navigation & Header -->
  <div class="mb-8">
    <a 
      hx-get="/dashboard" 
      hx-target="body" 
      hx-push-url="true" 
      class="inline-flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors cursor-pointer mb-4"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path>
      </svg>
      Back to Nodes Dashboard
    </a>
    
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-3">
          <h1 class="text-3xl font-bold text-white font-outfit">hk-relay-01</h1>
          <div class="flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-teal-950/40 border border-teal-500/25">
            <span class="status-pulse-online"></span>
            <span class="text-[10px] font-bold tracking-wider text-teal-400 uppercase">CONNECTED</span>
          </div>
        </div>
        <p class="text-sm font-mono text-gray-400 mt-1">IP Address: 47.242.88.190 | UFW status: active</p>
      </div>

      <!-- Quick Node Actions -->
      <div class="flex items-center gap-3">
        <button 
          hx-post="/api/node/hk-relay-01/reload-ufw" 
          hx-target="#ufw-status-box" 
          class="bg-gray-800 hover:bg-gray-700 text-xs font-semibold text-gray-300 py-2.5 px-4 rounded-lg transition-all"
        >
          Reload UFW Firewall
        </button>
      </div>
    </div>
  </div>

  <div id="ufw-status-box">
    <!-- Active UFW Rules Grid Container -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      
      <!-- MAIN COMPONENT: Port Rules Grid (Left/Center 2 cols) -->
      <div class="lg:col-span-2">
        <h2 class="text-lg font-bold text-white font-outfit mb-4 flex items-center gap-2">
          <span>Active Service Port Cards</span>
          <span class="px-2 py-0.5 text-xs bg-gray-800 text-gray-400 rounded-full font-normal">3 Ports</span>
        </h2>

        <!-- Port Cards Grid -->
        <div id="port-cards-container" class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <!-- Port cards dynamically rendered here -->
          <!-- Port 22 Card -->
          <div class="glass-card p-5 flex flex-col justify-between h-full relative overflow-hidden group/card" id="port-card-22">
            <div class="absolute inset-0 bg-gradient-to-br from-purple-600/5 via-transparent to-transparent opacity-0 group-hover/card:opacity-100 transition-opacity pointer-events-none"></div>
            <div>
              <div class="flex justify-between items-start mb-4 relative z-10">
                <div>
                  <div class="text-2xl font-extrabold text-white font-mono tracking-tight flex items-baseline gap-1">
                    22 <span class="text-xs font-normal text-purple-400">/tcp</span>
                  </div>
                  <span class="inline-block mt-1.5 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-purple-300 bg-purple-950/60 border border-purple-500/25 rounded">
                    SSH Access
                  </span>
                </div>
                <button 
                  hx-delete="/api/node/hk-relay-01/port/22" 
                  hx-confirm="Are you sure you want to close port 22 and remove all its whitelists?"
                  hx-target="#port-cards-container"
                  hx-swap="innerHTML"
                  class="text-gray-500 hover:text-red-400 p-1.5 rounded-lg hover:bg-red-950/20 transition-all"
                  title="Close Port"
                >
                  <svg class="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                  </svg>
                </button>
              </div>
              <div class="mb-5 relative z-10">
                <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider mb-2">Whitelisted Source IPs</div>
                <div class="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto pr-1">
                  <span class="inline-flex items-center gap-1.5 pl-2.5 pr-1 py-1 text-xs font-mono rounded-md bg-gray-800/80 border border-gray-700/60 text-gray-200">
                    <span>any</span>
                    <span class="text-[10px] text-gray-400">(Public)</span>
                  </span>
                </div>
              </div>
            </div>
            <div class="border-t border-gray-800/60 pt-4 mt-auto relative z-10">
              <form 
                hx-post="/api/node/hk-relay-01/port/22/ip" 
                hx-target="#port-card-22" 
                hx-swap="outerHTML"
                class="flex gap-2"
              >
                <input 
                  type="text" 
                  name="ip" 
                  placeholder="IP or Group..." 
                  required 
                  class="flex-1 min-w-0 bg-gray-900/80 border border-gray-800 text-xs text-white rounded-md px-2.5 py-1.5 focus:outline-none focus:border-purple-500 font-mono"
                />
                <input 
                  type="text" 
                  name="comment" 
                  placeholder="Comment" 
                  class="w-1/3 min-w-0 bg-gray-900/80 border border-gray-800 text-xs text-white rounded-md px-2.5 py-1.5 focus:outline-none focus:border-purple-500"
                />
                <button 
                  type="submit" 
                  class="bg-purple-600/90 hover:bg-purple-600 text-white px-3 py-1.5 text-xs font-semibold rounded-md transition-colors"
                >
                  + Add
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>

      <!-- SIDEBAR FORM: Open New Port Form (Right 1 col) -->
      <div class="lg:col-span-1">
        <div class="sticky top-6">
          <div class="glass-card p-6 border-purple-500/20 shadow-glow-purple">
            <div class="flex items-center gap-2 mb-4">
              <span class="text-xl">➕</span>
              <h3 class="text-lg font-bold text-white font-outfit">Open New Service Port</h3>
            </div>
            <form 
              hx-post="/api/node/hk-relay-01/port" 
              hx-target="#port-cards-container" 
              hx-swap="beforeend"
              class="space-y-4"
            >
              <div class="grid grid-cols-3 gap-3">
                <div class="col-span-2">
                  <label class="block text-[10px] font-bold text-gray-400 uppercase mb-1">Port</label>
                  <input 
                    type="number" 
                    name="port" 
                    placeholder="e.g. 8388" 
                    required 
                    class="w-full bg-gray-950 border border-gray-850 text-sm text-white font-mono rounded-lg px-3 py-2 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label class="block text-[10px] font-bold text-gray-400 uppercase mb-1">Protocol</label>
                  <select 
                    name="protocol" 
                    class="w-full bg-gray-950 border border-gray-850 text-sm text-white rounded-lg px-2.5 py-2 focus:outline-none focus:border-purple-500"
                  >
                    <option value="tcp">TCP</option>
                    <option value="udp">UDP</option>
                    <option value="both">Both</option>
                  </select>
                </div>
              </div>
              <div>
                <label class="block text-[10px] font-bold text-gray-400 uppercase mb-1">Service Type Tag</label>
                <select 
                  name="tag" 
                  class="w-full bg-gray-950 border border-gray-850 text-sm text-white rounded-lg px-3 py-2 focus:outline-none focus:border-purple-500"
                >
                  <option value="Custom Rule">Custom Rule</option>
                  <option value="Snell Proxy">Snell Proxy</option>
                  <option value="SSH Access">SSH Access</option>
                </select>
              </div>
              <div class="border-t border-gray-800 my-4 pt-3">
                <span class="text-xs text-purple-400 font-semibold mb-2 block">Optional: Initial Whitelist</span>
                <div class="space-y-3">
                  <div>
                    <label class="block text-[10px] text-gray-400 uppercase mb-1">Source IP / CIDR</label>
                    <input 
                      type="text" 
                      name="initial_ip" 
                      placeholder="e.g. 1.2.3.4" 
                      class="w-full bg-gray-950 border border-gray-850 text-sm text-white font-mono rounded-lg px-3 py-2 focus:outline-none focus:border-purple-500"
                    />
                  </div>
                  <div>
                    <label class="block text-[10px] text-gray-400 uppercase mb-1">IP Label (Alias)</label>
                    <input 
                      type="text" 
                      name="initial_ip_label" 
                      placeholder="e.g. Home" 
                      class="w-full bg-gray-950 border border-gray-850 text-sm text-white rounded-lg px-3 py-2 focus:outline-none focus:border-purple-500"
                    />
                  </div>
                </div>
              </div>
              <button 
                type="submit" 
                class="w-full bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white font-bold py-2.5 px-4 rounded-lg shadow-lg hover:shadow-purple-500/20 transition-all font-outfit text-sm"
              >
                Authorize & Open Port
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
```

---

### Core Component: "Port Card"

Each port is displayed as a premium card containing protocol badges, service category tags, removable whitelisted IP pills, a dynamic fast-allow input, and a destructive delete action.

```html
<!-- Port Card Template -->
<div class="glass-card p-5 flex flex-col justify-between h-full relative overflow-hidden group/card" id="port-card-28261">
  <!-- Subtle back-glow indicating active state -->
  <div class="absolute inset-0 bg-gradient-to-br from-purple-600/5 via-transparent to-transparent opacity-0 group-hover/card:opacity-100 transition-opacity pointer-events-none"></div>

  <div>
    <!-- 1. Card Header: Port badge & type tagging -->
    <div class="flex justify-between items-start mb-4 relative z-10">
      <div>
        <div class="text-2xl font-extrabold text-white font-mono tracking-tight flex items-baseline gap-1">
          28261 <span class="text-xs font-normal text-purple-400">/udp</span>
        </div>
        <!-- Type Tag -->
        <span class="inline-block mt-1.5 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-purple-300 bg-purple-950/60 border border-purple-500/25 rounded">
          Snell Proxy
        </span>
      </div>
      
      <!-- Close entire Port -->
      <button 
        hx-delete="/api/node/hk-relay-01/port/28261" 
        hx-confirm="Are you sure you want to close port 28261 and remove all its whitelists?"
        hx-target="#port-cards-container"
        hx-swap="innerHTML"
        class="text-gray-500 hover:text-red-400 p-1.5 rounded-lg hover:bg-red-950/20 transition-all"
        title="Close Port (Delete all rules)"
      >
        <svg class="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
        </svg>
      </button>
    </div>

    <!-- 2. Card Body: Whitelisted Source IPs/Pills -->
    <div class="mb-5 relative z-10">
      <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider mb-2">Whitelisted Source IPs</div>
      
      <div class="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto pr-1">
        <!-- Whitelisted IP Pill (Home) -->
        <span class="inline-flex items-center gap-1.5 pl-2.5 pr-1 py-1 text-xs font-mono rounded-md bg-gray-800/80 border border-gray-700/60 text-gray-200">
          <span>1.2.3.4</span>
          <span class="text-[10px] text-gray-400">(Home)</span>
          <button 
            hx-delete="/api/node/hk-relay-01/port/28261/ip/1.2.3.4" 
            hx-target="#port-card-28261" 
            hx-swap="outerHTML"
            class="hover:text-red-400 text-gray-500 p-0.5 rounded transition-colors"
          >
            ✕
          </button>
        </span>

        <!-- Whitelisted IP Pill (NL Proxy) -->
        <span class="inline-flex items-center gap-1.5 pl-2.5 pr-1 py-1 text-xs font-mono rounded-md bg-gray-800/80 border border-gray-700/60 text-gray-200">
          <span>5.6.7.8</span>
          <span class="text-[10px] text-gray-400">(NL Proxy)</span>
          <button 
            hx-delete="/api/node/hk-relay-01/port/28261/ip/5.6.7.8" 
            hx-target="#port-card-28261" 
            hx-swap="outerHTML"
            class="hover:text-red-400 text-gray-500 p-0.5 rounded transition-colors"
          >
            ✕
          </button>
        </span>
      </div>
    </div>
  </div>

  <!-- 3. Card Actions: Inline small form to add IP -->
  <div class="border-t border-gray-800/60 pt-4 mt-auto relative z-10">
    <form 
      hx-post="/api/node/hk-relay-01/port/28261/ip" 
      hx-target="#port-card-28261" 
      hx-swap="outerHTML"
      class="flex gap-2"
    >
      <input 
        type="text" 
        name="ip" 
        placeholder="IP or Group..." 
        required 
        class="flex-1 min-w-0 bg-gray-900/80 border border-gray-800 text-xs text-white rounded-md px-2.5 py-1.5 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 font-mono"
      />
      <input 
        type="text" 
        name="comment" 
        placeholder="Comment" 
        class="w-1/3 min-w-0 bg-gray-900/80 border border-gray-800 text-xs text-white rounded-md px-2.5 py-1.5 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500"
      />
      <button 
        type="submit" 
        class="bg-purple-600/90 hover:bg-purple-600 text-white px-3 py-1.5 text-xs font-semibold rounded-md transition-colors"
      >
        + Add
      </button>
    </form>
  </div>
</div>
```

---

## 4. HTMX Routes & Partials Plan

To avoid full-page refreshes, the app maps all interactive steps to simple REST endpoints returning HTML partial fragments:

| Action / Operation | HTMX Attributes | Trigger / Target | Return Response | Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **View Dashboard** | `hx-get="/api/nodes"` | Trigger: `load`<br>Target: `#nodes-grid` | List of HTML node card partials. | Hydrates the dashboard grid asynchronously. |
| **Refresh Telemetry** | `hx-post="/api/nodes/sync-all"` | Trigger: `click`<br>Target: `#nodes-grid` | Re-rendered list of nodes. | Animates progress spinner via `.htmx-request` rule. |
| **Delete/Close Port** | `hx-delete="/api/node/{id}/port/{port}"` | Trigger: `click`<br>Target: `#port-cards-container` | Updated collection list of active port cards. | Instantly slides out/removes the deleted card from layout. |
| **Remove Whitelist IP** | `hx-delete="/api/node/{id}/port/{port}/ip/{ip}"` | Trigger: `click`<br>Target: `closest .glass-card` | Single updated Port Card element (outer HTML replacement). | Removes the targeted IP badge without touching other port cards. |
| **Add Whitelist IP** | `hx-post="/api/node/{id}/port/{port}/ip"` | Trigger: `submit`<br>Target: `closest .glass-card` | Single updated Port Card element. | Appends new IP pill dynamically, resetting the inline form fields. |
| **Open New Port** | `hx-post="/api/node/{id}/port"` | Trigger: `submit`<br>Target: `#port-cards-container`<br>Swap: `beforeend` | Newly created Port Card element. | Appends the new card directly into the layout grid. |
| **Full Reload UFW** | `hx-post="/api/node/{id}/reload-ufw"` | Trigger: `click`<br>Target: `#ufw-status-box` | Entire refreshed status box structure. | Re-queries the VPS node backend to confirm rules are written. |

---

### UX Implementation Guidelines
1. **Targeting**: When adding/removing an IP from a port card, always return the *entire* single card partial and replace it with `hx-swap="outerHTML"`. This ensures server-side tag validation updates and correctly updates form targets.
2. **Transition Effects**: Let standard CSS handles list animations using transitions:
   ```css
   #port-cards-container > * {
     transition: transform 0.25s ease, opacity 0.25s ease;
   }
   .htmx-swapping {
     opacity: 0;
     transform: scale(0.9);
   }
   ```
3. **Optimistic States / Disabling**: Use client-side indicators or disabled forms during processing. For instance, when adding an IP, disable inputs during flight using Tailwind `disabled:opacity-50` triggers.
