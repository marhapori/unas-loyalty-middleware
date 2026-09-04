(function () {
  "use strict";

  const scanInput = document.getElementById("scan-input");
  const scanStatus = document.getElementById("scan-status");
  const customerPanel = document.getElementById("customer-panel");
  const customerName = document.getElementById("customer-name");
  const customerCard = document.getElementById("customer-card");
  const customerBalance = document.getElementById("customer-balance");
  const offlineIndicator = document.getElementById("offline-indicator");

  const earnAmount = document.getElementById("earn-amount");
  const earnPreview = document.getElementById("earn-preview");
  const earnReceipt = document.getElementById("earn-receipt");
  const earnButton = document.getElementById("earn-button");

  const redeemPoints = document.getElementById("redeem-points");
  const redeemPreview = document.getElementById("redeem-preview");
  const redeemReceipt = document.getElementById("redeem-receipt");
  const redeemButton = document.getElementById("redeem-button");

  const resetButton = document.getElementById("reset-button");
  const refreshHistoryButton = document.getElementById("refresh-history");
  const historyList = document.getElementById("history-list");

  const modal = document.getElementById("confirm-modal");
  const confirmTitle = document.getElementById("confirm-title");
  const confirmBody = document.getElementById("confirm-body");
  const confirmOk = document.getElementById("confirm-ok");
  const confirmCancel = document.getElementById("confirm-cancel");

  let currentQrPayload = null;
  let currentBalance = null;
  let lastScan = { payload: null, at: 0 };
  let config = null;
  const isAdmin = document.body.dataset.role === "admin";

  function focusScan() {
    scanInput.value = "";
    scanInput.focus();
  }

  function showStatus(message, kind) {
    scanStatus.textContent = message;
    scanStatus.className = "status-banner status-" + kind;
    scanStatus.hidden = false;
  }

  function clearStatus() {
    scanStatus.hidden = true;
  }

  async function api(path, options) {
    options = options || {};
    options.headers = Object.assign(
      { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      options.headers || {}
    );
    let response;
    try {
      response = await fetch(path, options);
    } catch (networkError) {
      offlineIndicator.hidden = false;
      throw new Error("UNAS kapcsolat nem elerheto - probald ujra");
    }
    offlineIndicator.hidden = true;
    if (!response.ok) {
      let detail = "Ismeretlen hiba (" + response.status + ")";
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch (_e) {
        /* ignore */
      }
      const err = new Error(detail);
      err.status = response.status;
      throw err;
    }
    if (response.status === 204) return null;
    return response.json();
  }

  function resetCustomerPanel() {
    currentQrPayload = null;
    currentBalance = null;
    customerPanel.hidden = true;
    earnAmount.value = "";
    redeemPoints.value = "";
    earnPreview.textContent = "";
    redeemPreview.textContent = "";
    clearStatus();
    focusScan();
  }

  function computeEarnPreview(amount) {
    if (!config || !amount || amount < 0) return 0;
    const raw = amount * config.pointsPerCurrencyUnit;
    if (config.pointsRounding === "ceil") return Math.ceil(raw);
    if (config.pointsRounding === "round") return Math.round(raw);
    return Math.floor(raw);
  }

  earnAmount.addEventListener("input", () => {
    const amount = parseFloat(earnAmount.value);
    const points = computeEarnPreview(amount);
    earnPreview.textContent = amount ? "Varhato jovairas: kb. " + points + " pont" : "";
  });

  redeemPoints.addEventListener("input", () => {
    const points = parseInt(redeemPoints.value, 10);
    if (!points || !config) {
      redeemPreview.textContent = "";
      return;
    }
    const value = points * config.redemptionValuePerPoint;
    redeemPreview.textContent = "Ertek: kb. " + value + " Ft";
  });

  async function handleScan(rawPayload) {
    const payload = (rawPayload || "").trim();
    if (!payload) return;

    const now = Date.now();
    if (lastScan.payload === payload && now - lastScan.at < 2000) {
      return; // duplicate fast re-scan, ignore
    }
    lastScan = { payload, at: now };

    clearStatus();
    showStatus("Betoltes...", "loading");
    try {
      const result = await api("/api/scans/resolve", {
        method: "POST",
        body: JSON.stringify({ qrPayload: payload }),
      });
      currentQrPayload = payload;
      currentBalance = parseInt(result.pointsBalance, 10);
      customerName.textContent = result.customer.displayName || "(nev nelkul)";
      customerCard.textContent = result.customer.maskedCardId;
      customerBalance.textContent = result.pointsBalance;
      customerPanel.hidden = false;
      clearStatus();
    } catch (err) {
      customerPanel.hidden = true;
      showStatus(err.message || "Hiba a beolvasas soran", "error");
    } finally {
      scanInput.value = "";
    }
  }

  scanInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleScan(scanInput.value);
    }
  });

  function openConfirm(title, body) {
    return new Promise((resolve) => {
      confirmTitle.textContent = title;
      confirmBody.textContent = body;
      modal.hidden = false;
      const cleanup = (result) => {
        modal.hidden = true;
        confirmOk.removeEventListener("click", onOk);
        confirmCancel.removeEventListener("click", onCancel);
        resolve(result);
      };
      const onOk = () => cleanup(true);
      const onCancel = () => cleanup(false);
      confirmOk.addEventListener("click", onOk);
      confirmCancel.addEventListener("click", onCancel);
    });
  }

  function randomKey() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return "k" + Math.random().toString(36).slice(2) + Date.now();
  }

  earnButton.addEventListener("click", async () => {
    if (!currentQrPayload) return;
    const amount = parseInt(earnAmount.value, 10);
    if (!amount || amount <= 0) {
      showStatus("Add meg a vasarlas osszeget", "error");
      return;
    }
    const previewPoints = computeEarnPreview(amount);
    const ok = await openConfirm(
      "Pont jovairasa",
      "Regi egyenleg: " + currentBalance + " pont. Varhato valtozas: +" + previewPoints +
        " pont. Uj egyenleg kb.: " + (currentBalance + previewPoints) + " pont."
    );
    if (!ok) return;

    const receipt = earnReceipt.value.trim() || ("REG-" + Date.now());
    showStatus("Feldolgozas...", "loading");
    try {
      const result = await api("/api/loyalty/earn", {
        method: "POST",
        body: JSON.stringify({
          qrPayload: currentQrPayload,
          externalReceiptId: receipt,
          purchaseAmountGross: amount,
          idempotencyKey: receipt + ":earn:" + randomKey(),
        }),
      });
      currentBalance = parseInt(result.balanceAfter, 10);
      customerBalance.textContent = result.balanceAfter;
      showStatus("Siker: uj egyenleg " + result.balanceAfter + " pont", "success");
      earnAmount.value = "";
      earnPreview.textContent = "";
      loadHistory();
    } catch (err) {
      showStatus(err.message || "Hiba a jovairas soran", "error");
    }
  });

  redeemButton.addEventListener("click", async () => {
    if (!currentQrPayload) return;
    const points = parseInt(redeemPoints.value, 10);
    if (!points || points <= 0) {
      showStatus("Add meg a bevaltando pontot", "error");
      return;
    }
    if (currentBalance !== null && points > currentBalance) {
      showStatus("Nincs eleg pont a bevaltashoz", "error");
      return;
    }
    const ok = await openConfirm(
      "Pont bevaltasa",
      "Regi egyenleg: " + currentBalance + " pont. Bevaltas: -" + points +
        " pont. Uj egyenleg kb.: " + (currentBalance - points) + " pont."
    );
    if (!ok) return;

    const receipt = redeemReceipt.value.trim() || ("REG-" + Date.now());
    showStatus("Feldolgozas...", "loading");
    try {
      const result = await api("/api/loyalty/redeem", {
        method: "POST",
        body: JSON.stringify({
          qrPayload: currentQrPayload,
          externalReceiptId: receipt,
          pointsToRedeem: points,
          idempotencyKey: receipt + ":redeem:" + randomKey(),
        }),
      });
      currentBalance = parseInt(result.balanceAfter, 10);
      customerBalance.textContent = result.balanceAfter;
      showStatus("Siker: uj egyenleg " + result.balanceAfter + " pont", "success");
      redeemPoints.value = "";
      redeemPreview.textContent = "";
      loadHistory();
    } catch (err) {
      showStatus(err.message || "Hiba a bevaltas soran", "error");
    }
  });

  resetButton.addEventListener("click", resetCustomerPanel);

  async function reverseTransaction(row) {
    const reason = window.prompt(
      "Visszavonas indoklasa (kotelezo) - " + row.type + " " + row.pointsDelta + " pont:"
    );
    if (reason === null) return; // cancelled
    if (reason.trim().length < 3) {
      showStatus("A visszavonas indoklasa legalabb 3 karakter legyen", "error");
      return;
    }
    try {
      const result = await api("/api/loyalty/transactions/" + row.id + "/reverse", {
        method: "POST",
        body: JSON.stringify({ reason: reason.trim() }),
      });
      showStatus("Visszavonva. Uj egyenleg: " + result.balanceAfter + " pont", "success");
      if (currentBalance !== null) {
        currentBalance = parseInt(result.balanceAfter, 10);
        customerBalance.textContent = result.balanceAfter;
      }
      loadHistory();
    } catch (err) {
      showStatus(err.message || "Hiba a visszavonas soran", "error");
    }
  }

  async function loadHistory() {
    try {
      const rows = await api("/api/loyalty/transactions?limit=15", { method: "GET" });
      historyList.innerHTML = "";
      rows.forEach((row) => {
        const li = document.createElement("li");
        li.className = "history-item history-" + row.type;

        const label = document.createElement("span");
        label.textContent =
          row.createdAt.replace("T", " ").slice(0, 19) +
          " - " + row.type + " - " + row.pointsDelta + " pont - " + row.status;
        li.appendChild(label);

        const canReverse = isAdmin && row.status === "applied" && (row.type === "earn" || row.type === "redeem");
        if (canReverse) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "link-button history-reverse-btn";
          button.textContent = "Visszavonas";
          button.addEventListener("click", () => reverseTransaction(row));
          li.appendChild(button);
        }

        historyList.appendChild(li);
      });
    } catch (_err) {
      /* history is a convenience panel, fail silently */
    }
  }

  refreshHistoryButton.addEventListener("click", loadHistory);

  async function init() {
    try {
      config = await api("/api/loyalty/config", { method: "GET" });
    } catch (_err) {
      /* config preview is best-effort; server still enforces authoritative rules */
    }
    loadHistory();

    const initialQrPayload = document.body.dataset.initialQrPayload;
    if (initialQrPayload) {
      // Arrived via /scan/<token> (seller scanned the customer's QR with their own
      // phone camera) - resolve immediately instead of waiting for keyboard input.
      // Strip the token out of the visible address bar/history afterwards so it
      // doesn't linger there any longer than necessary.
      window.history.replaceState({}, document.title, "/register");
      await handleScan(initialQrPayload);
    } else {
      focusScan();
    }
  }

  init();
})();
