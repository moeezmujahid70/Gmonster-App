<?php
/**
 * Plugin Name: Gmonster Renewal Sync
 * Description: Sends successful WooCommerce subscription renewals to the Gmonster backend.
 * Version: 1.0.0
 * Requires Plugins: woocommerce, woocommerce-subscriptions
 */

if (!defined('ABSPATH')) {
    exit;
}

const GMONSTER_RENEWAL_SYNC_GROUP = 'gmonster-renewal-sync';

function gmonster_renewal_sync_is_configured() {
    return defined('GMONSTER_RENEWAL_ENDPOINT')
        && defined('GMONSTER_RENEWAL_WEBHOOK_SECRET')
        && GMONSTER_RENEWAL_ENDPOINT !== ''
        && GMONSTER_RENEWAL_WEBHOOK_SECRET !== '';
}

function gmonster_renewal_sync_add_order_note($renewal_order, $message) {
    if ($renewal_order instanceof WC_Order) {
        $renewal_order->add_order_note($message, false);
    }
}

function gmonster_renewal_sync_schedule_retry($subscription_id, $renewal_order_id, $attempt, $renewal_order) {
    $delays = array(300, 900, 3600, 21600, 86400);
    if ($attempt >= count($delays)) {
        gmonster_renewal_sync_add_order_note(
            $renewal_order,
            'Gmonster renewal sync: delivery failed after five retries. Review server logs.'
        );
        error_log('Gmonster renewal sync exhausted retries for renewal order ' . $renewal_order_id . '.');
        return;
    }

    if (!function_exists('as_schedule_single_action')) {
        gmonster_renewal_sync_add_order_note(
            $renewal_order,
            'Gmonster renewal sync: delivery failed and retries are unavailable. Review server logs.'
        );
        error_log('Gmonster renewal sync cannot schedule a retry because Action Scheduler is unavailable.');
        return;
    }

    as_schedule_single_action(
        time() + $delays[$attempt],
        'gmonster_renewal_sync_dispatch',
        array($subscription_id, $renewal_order_id, $attempt + 1),
        GMONSTER_RENEWAL_SYNC_GROUP
    );
}

function gmonster_renewal_sync_dispatch($subscription_id, $renewal_order_id, $attempt = 0) {
    if (!gmonster_renewal_sync_is_configured()) {
        error_log('Gmonster renewal sync is not configured.');
        return;
    }

    if (!function_exists('wcs_get_subscription') || !function_exists('wc_get_order')) {
        error_log('Gmonster renewal sync requires WooCommerce Subscriptions.');
        return;
    }

    $subscription = wcs_get_subscription($subscription_id);
    $renewal_order = wc_get_order($renewal_order_id);
    if (!$subscription || !$renewal_order) {
        error_log('Gmonster renewal sync could not load subscription or renewal order.');
        return;
    }

    $body = wp_json_encode(array(
        'subscription_id' => (int) $subscription->get_id(),
        'renewal_order_id' => (int) $renewal_order->get_id(),
        'billing_email' => $renewal_order->get_billing_email(),
    ));
    if ($body === false) {
        gmonster_renewal_sync_add_order_note(
            $renewal_order,
            'Gmonster renewal sync: could not encode the renewal event.'
        );
        return;
    }

    $timestamp = (string) time();
    $signature = hash_hmac(
        'sha256',
        $timestamp . '.' . $body,
        GMONSTER_RENEWAL_WEBHOOK_SECRET
    );
    $response = wp_remote_post(GMONSTER_RENEWAL_ENDPOINT, array(
        'timeout' => 15,
        'headers' => array(
            'Content-Type' => 'application/json',
            'X-Gmonster-Timestamp' => $timestamp,
            'X-Gmonster-Signature' => $signature,
        ),
        'body' => $body,
    ));

    if (is_wp_error($response)) {
        error_log('Gmonster renewal sync request failed: ' . $response->get_error_message());
        gmonster_renewal_sync_schedule_retry(
            $subscription_id,
            $renewal_order_id,
            $attempt,
            $renewal_order
        );
        return;
    }

    $status_code = wp_remote_retrieve_response_code($response);
    if ($status_code === 200) {
        return;
    }

    if ($status_code === 202) {
        gmonster_renewal_sync_add_order_note(
            $renewal_order,
            'Gmonster renewal sync: subscription is not linked to a Gmonster account.'
        );
        return;
    }

    if ($status_code === 400 || $status_code === 401) {
        gmonster_renewal_sync_add_order_note(
            $renewal_order,
            'Gmonster renewal sync: request rejected by backend. Check plugin configuration.'
        );
        return;
    }

    if ($status_code >= 500 && $status_code <= 599) {
        error_log('Gmonster renewal sync backend returned HTTP ' . $status_code . '.');
        gmonster_renewal_sync_schedule_retry(
            $subscription_id,
            $renewal_order_id,
            $attempt,
            $renewal_order
        );
        return;
    }

    gmonster_renewal_sync_add_order_note(
        $renewal_order,
        'Gmonster renewal sync: backend returned an unexpected response. Review server logs.'
    );
}

function gmonster_renewal_sync_queue_renewal($subscription, $renewal_order) {
    if (!gmonster_renewal_sync_is_configured()) {
        error_log('Gmonster renewal sync is not configured.');
        return;
    }

    if (!$subscription instanceof WC_Subscription || !$renewal_order instanceof WC_Order) {
        error_log('Gmonster renewal sync received an invalid renewal payload.');
        return;
    }

    $args = array((int) $subscription->get_id(), (int) $renewal_order->get_id(), 0);
    if (function_exists('as_enqueue_async_action')) {
        as_enqueue_async_action(
            'gmonster_renewal_sync_dispatch',
            $args,
            GMONSTER_RENEWAL_SYNC_GROUP
        );
        return;
    }

    gmonster_renewal_sync_add_order_note(
        $renewal_order,
        'Gmonster renewal sync: delivery could not be queued. Review server logs.'
    );
    error_log('Gmonster renewal sync cannot queue delivery because Action Scheduler is unavailable.');
}

function gmonster_renewal_sync_bootstrap() {
    if (!gmonster_renewal_sync_is_configured()) {
        error_log('Gmonster renewal sync requires endpoint and webhook-secret constants in wp-config.php.');
        return;
    }

    add_action(
        'woocommerce_subscription_renewal_payment_complete',
        'gmonster_renewal_sync_queue_renewal',
        10,
        2
    );
    add_action(
        'gmonster_renewal_sync_dispatch',
        'gmonster_renewal_sync_dispatch',
        10,
        3
    );
}

add_action('plugins_loaded', 'gmonster_renewal_sync_bootstrap', 20);
