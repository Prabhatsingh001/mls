// Service Worker – handles incoming push events and notification clicks.
// Served from /sw.js  (see notification/urls.py)

self.addEventListener("push", function (event) {
  let data = { title: "MLS Notification", body: "", url: "/notifications/" };
  if (event.data) {
    try {
      data = event.data.json();
    } catch (_) {
      data.body = event.data.text();
    }
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/static/icon-192.png",
      badge: "/static/icon-192.png",
      data: { url: data.url || "/notifications/" },
    })
  );
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  const target = event.notification.data.url || "/notifications/";
  event.waitUntil(clients.openWindow(target));
});
