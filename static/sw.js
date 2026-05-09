// Service Worker for Liberty Basketball PWA
// Handles push notifications and offline caching

const CACHE_NAME = 'liberty-basketball-v1';
const OFFLINE_URLS = [
  '/',
  '/login',
  '/register',
  '/static/css/style.css',
];

// Install: cache core assets
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(OFFLINE_URLS);
    })
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(key) { return key !== CACHE_NAME; })
            .map(function(key) { return caches.delete(key); })
      );
    })
  );
  self.clients.claim();
});

// Fetch: network-first, fallback to cache
self.addEventListener('fetch', function(event) {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request).catch(function() {
      return caches.match(event.request);
    })
  );
});

// Push: show notification
self.addEventListener('push', function(event) {
  var data = {};
  try { data = event.data.json(); } catch(e) {}

  var title = data.title || 'Liberty Basketball';
  var options = {
    body: data.body || 'You have a new notification',
    icon: '/static/img/patriot-logo.jpg',
    badge: '/static/img/patriot-logo.jpg',
    data: data.link || '/',
    actions: [
      { action: 'open', title: 'Open' },
      { action: 'dismiss', title: 'Dismiss' },
    ],
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// Notification click: open relevant page
self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  var url = event.notification.data || '/';
  if (event.action === 'dismiss') return;

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(windowClients) {
      // Focus existing tab if open
      for (var i = 0; i < windowClients.length; i++) {
        if (windowClients[i].url.indexOf(url) !== -1 && 'focus' in windowClients[i]) {
          return windowClients[i].focus();
        }
      }
      // Otherwise open new tab
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});
