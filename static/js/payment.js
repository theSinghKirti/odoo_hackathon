/**
 * Subly Payment & Razorpay Checkout Integration (Milestone F8)
 * Vanilla JavaScript implementation adhering to Subly frontend standards.
 */

// 1. Offline Payment Modal Handlers
function openPaymentModal() {
  const modal = document.getElementById('payment-modal');
  if (modal) {
    modal.style.display = 'flex';
  } else {
    // If modal not in DOM, request via HTMX
    if (window.htmx) {
      window.htmx.ajax('GET', window.location.pathname + '/payment-modal', {
        target: '#modal-container',
        swap: 'innerHTML'
      });
    }
  }
}

function closePaymentModal() {
  const modal = document.getElementById('payment-modal');
  if (modal) {
    modal.style.display = 'none';
  }
}

// 2. Dynamic Conditional Fields Switcher
function togglePaymentMethodFields(method) {
  const blocks = document.querySelectorAll('.method-specific-block');
  blocks.forEach(block => {
    block.style.display = 'none';
  });

  const activeBlock = document.getElementById('fields-' + method);
  if (activeBlock) {
    activeBlock.style.display = 'block';
  }
}

// 3. Client-side Offline Payment Validation
function validateOfflinePayment() {
  const amountInput = document.getElementById('payment_amount');
  if (!amountInput) return true;

  const amount = parseFloat(amountInput.value);
  const maxAmount = parseFloat(amountInput.getAttribute('max')) || Infinity;

  if (isNaN(amount) || amount <= 0) {
    alert('Please enter a valid payment amount greater than zero.');
    amountInput.focus();
    return false;
  }

  if (amount > maxAmount + 0.001) {
    alert('Payment amount cannot exceed the remaining balance of ₹' + maxAmount.toFixed(2));
    amountInput.focus();
    return false;
  }

  const submitBtn = document.getElementById('btn-submit-offline-payment');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = 'Recording...';
  }

  return true;
}

// 4. Razorpay Online Checkout Flow
async function initiateRazorpayPayment(invoiceId) {
  const payBtn = document.getElementById('btn-pay-online');
  const originalText = payBtn ? payBtn.innerHTML : '';

  try {
    if (payBtn) {
      payBtn.disabled = true;
      payBtn.innerHTML = '<span style="display:inline-block; animation:spin 1s linear infinite;">&#9696;</span> Generating Order...';
    }

    // Step 1: Request Razorpay Order from server
    const orderResponse = await fetch(`/web/invoices/${invoiceId}/razorpay/order`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      }
    });

    if (!orderResponse.ok) {
      const errData = await orderResponse.json().catch(() => ({}));
      throw new Error(errData.detail || 'Could not initiate Razorpay order with server.');
    }

    const orderData = await orderResponse.json();

    // Step 2: Ensure Razorpay SDK is loaded
    if (typeof Razorpay === 'undefined') {
      // In development fallback if external CDN is blocked
      console.warn('Razorpay SDK not loaded from CDN, running simulated test checkout mode.');
      simulateMockPaymentFlow(invoiceId, orderData);
      return;
    }

    // Step 3: Configure Razorpay Checkout options
    const options = {
      key: orderData.key_id,
      amount: orderData.amount, // in paise
      currency: orderData.currency || 'INR',
      name: 'Brightloop Software',
      description: `Payment for Invoice ${orderData.invoice_number}`,
      image: '/static/img/logo.png',
      order_id: orderData.order_id,
      prefill: {
        name: orderData.customer_name || '',
        email: orderData.customer_email || '',
      },
      theme: {
        color: '#07998E' // Subly primary teal
      },
      handler: async function (response) {
        // Step 4: Submit verification payload to backend HMAC verification endpoint
        await verifyRazorpayPayment(invoiceId, response);
      },
      modal: {
        ondismiss: function () {
          if (payBtn) {
            payBtn.disabled = false;
            payBtn.innerHTML = originalText;
          }
        }
      }
    };

    const rzp = new Razorpay(options);
    rzp.on('payment.failed', function (response) {
      renderPaymentFeedback('failure', {
        error: response.error ? response.error.description : 'Payment transaction failed or was declined by issuing bank.',
        invoice_id: invoiceId
      });
      if (payBtn) {
        payBtn.disabled = false;
        payBtn.innerHTML = originalText;
      }
    });

    rzp.open();

  } catch (error) {
    console.error('Razorpay initialization error:', error);
    renderPaymentFeedback('failure', {
      error: error.message || 'Payment service is temporarily unreachable.',
      invoice_id: invoiceId
    });
    if (payBtn) {
      payBtn.disabled = false;
      payBtn.innerHTML = originalText;
    }
  }
}

// 5. Server-side HMAC Signature Verification Handler
async function verifyRazorpayPayment(invoiceId, response) {
  const payBtn = document.getElementById('btn-pay-online');
  try {
    if (payBtn) {
      payBtn.innerHTML = '<span style="display:inline-block; animation:spin 1s linear infinite;">&#9696;</span> Verifying HMAC...';
    }

    const verifyResponse = await fetch(`/web/invoices/${invoiceId}/razorpay/verify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({
        razorpay_order_id: response.razorpay_order_id,
        razorpay_payment_id: response.razorpay_payment_id,
        razorpay_signature: response.razorpay_signature
      })
    });

    const result = await verifyResponse.json();

    if (verifyResponse.ok && result.status === 'success') {
      // Reload page or swap HTMX detail
      renderPaymentFeedback('success', {
        message: 'Payment verified and settled successfully via Razorpay.',
        payment_reference: response.razorpay_payment_id,
        amount_paid: result.amount_paid,
        remaining_balance: result.amount_due
      });

      // Refresh invoice page after brief moment so user sees feedback
      setTimeout(() => {
        window.location.reload();
      }, 1500);
    } else {
      renderPaymentFeedback('failure', {
        error: result.detail || result.message || 'Authoritative cryptographic signature verification failed.',
        invoice_id: invoiceId
      });
      if (payBtn) {
        payBtn.disabled = false;
        payBtn.innerHTML = 'Pay Online';
      }
    }
  } catch (err) {
    console.error('Verification error:', err);
    renderPaymentFeedback('failure', {
      error: 'Network error communicating with payment verification server.',
      invoice_id: invoiceId
    });
    if (payBtn) {
      payBtn.disabled = false;
      payBtn.innerHTML = 'Pay Online';
    }
  }
}

// 6. Test Development Simulator (Fallback when network restricts external Razorpay popup)
function simulateMockPaymentFlow(invoiceId, orderData) {
  const mockPaymentId = 'pay_sim_' + Math.random().toString(36).substring(2, 10);
  const proceed = confirm(
    `[Simulated Razorpay Checkout Mode]\n` +
    `Order ID: ${orderData.order_id}\n` +
    `Amount: ₹${(orderData.amount / 100).toFixed(2)}\n\n` +
    `Click OK to simulate successful card/UPI authorization.`
  );

  if (proceed) {
    verifyRazorpayPayment(invoiceId, {
      razorpay_order_id: orderData.order_id,
      razorpay_payment_id: mockPaymentId,
      razorpay_signature: 'simulated_hmac_signature'
    });
  } else {
    const payBtn = document.getElementById('btn-pay-online');
    if (payBtn) {
      payBtn.disabled = false;
      payBtn.innerHTML = 'Pay Online';
    }
  }
}

// 7. Dynamic Feedback Renderer
function renderPaymentFeedback(status, data) {
  let target = document.getElementById('payment-feedback-target');
  if (!target) {
    target = document.createElement('div');
    target.id = 'payment-feedback-target';
    const mainWrapper = document.getElementById('invoice-detail-wrapper');
    if (mainWrapper) {
      mainWrapper.insertBefore(target, mainWrapper.firstChild);
    }
  }

  let html = '';
  if (status === 'success') {
    html = `
      <div style="background-color: var(--pastel-mint); border: 1px solid #A7F3D0; border-radius: var(--radius-card); padding: var(--space-5); margin-bottom: var(--space-4); display: flex; align-items: flex-start; gap: 14px;">
        <div style="width: 36px; height: 36px; border-radius: 50%; background-color: #059669; color: white; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
        </div>
        <div style="flex: 1;">
          <h3 style="font-size: 1.05rem; font-weight: 700; color: #065F46; margin: 0 0 2px 0;">Payment Successful!</h3>
          <p style="font-size: 0.85rem; color: #047857; margin: 0 0 8px 0;">${data.message || 'Payment verified and settled.'}</p>
          <div style="font-size: 0.8rem; color: #065F46;">Ref: <strong>${data.payment_reference || 'PAID'}</strong></div>
        </div>
      </div>
    `;
  } else {
    html = `
      <div style="background-color: var(--pastel-pink); border: 1px solid #FECACA; border-radius: var(--radius-card); padding: var(--space-5); margin-bottom: var(--space-4); display: flex; align-items: flex-start; gap: 14px;">
        <div style="width: 36px; height: 36px; border-radius: 50%; background-color: var(--danger); color: white; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </div>
        <div style="flex: 1;">
          <h3 style="font-size: 1.05rem; font-weight: 700; color: #991B1B; margin: 0 0 2px 0;">Payment Could Not Be Completed</h3>
          <p style="font-size: 0.85rem; color: #B91C1C; margin: 0 0 10px 0;">${data.error || 'Payment was cancelled or failed.'}</p>
          <button type="button" class="btn btn-outline" onclick="initiateRazorpayPayment(${data.invoice_id});" style="color: var(--danger); border-color: #F87171; padding: 4px 12px; font-size: 0.8rem; background: white;">
            Retry Payment
          </button>
        </div>
      </div>
    `;
  }
  target.innerHTML = html;
}
