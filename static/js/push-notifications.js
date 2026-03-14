// push-notifications.js – registers service worker & subscribes to Web Push.
// Include this script in the base template for authenticated users.

(function () {
  "use strict";

  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    return; // browser doesn't support push
  }

  // Utility: convert a URL-safe base64 VAPID key to a Uint8Array
  function urlBase64ToUint8Array(base64String) {
    var padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    var rawData = atob(base64);
    var outputArray = new Uint8Array(rawData.length);
    for (var i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  function getCookie(name) {
    var cookies = document.cookie.split(";");
    for (var i = 0; i < cookies.length; i++) {
      var c = cookies[i].trim();
      if (c.startsWith(name + "=")) {
        return decodeURIComponent(c.substring(name.length + 1));
      }
    }
    return null;
  }

  navigator.serviceWorker
    .register("/static/sw.js")
    .then(function (registration) {
      return registration.pushManager.getSubscription().then(function (sub) {
        if (sub) return sub; // already subscribed

        // Fetch the server's VAPID public key
        return fetch("/notifications/push/vapid-key/")
          .then(function (r) { return r.json(); })
          .then(function (data) {
            return registration.pushManager.subscribe({
              userVisibleOnly: true,
              applicationServerKey: urlBase64ToUint8Array(data.public_key),
            });
          });
      });
    })
    .then(function (subscription) {
      if (!subscription) return;
      // Send the subscription to the server
      var body = JSON.stringify(subscription.toJSON());
      return fetch("/notifications/push/subscribe/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: body,
      });
    })
    .catch(function (err) {
      // Silently ignore – push is a progressive enhancement
      console.warn("Push subscription failed:", err);
    });
})();
