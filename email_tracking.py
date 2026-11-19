import re


def build_tracking_php(measurement_id: str, api_secret: str) -> str:
    measurement_id = measurement_id.strip()
    if not re.fullmatch(r"G-[A-Z0-9]+", measurement_id):
        raise ValueError("Enter the Web stream Measurement ID starting with G-.")
    api_secret = api_secret.strip()
    if not api_secret:
        raise ValueError("Enter the Measurement Protocol API secret from the same Web stream.")

    escaped_secret = api_secret.replace("\\", "\\\\").replace("'", "\\'")
    return (
        "<?php\n"
        f"$measurement_id = '{measurement_id}';\n"
        f"$api_secret = '{escaped_secret}';\n"
        + _PIXEL_SCRIPT
    )


_PIXEL_SCRIPT = r"""
ini_set('display_errors', '0');
header('Content-Type: image/gif');
header('Cache-Control: no-store');
echo base64_decode('R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==');

if (!function_exists('curl_init')) {
    error_log('Email tracking requires the PHP cURL extension.');
    return;
}

$client_id = $_GET['client_id'] ?? '';
if (!is_string($client_id) || !preg_match('/^[1-9][0-9]*\.[1-9][0-9]*$/D', $client_id)) {
    $client_id = random_int(1, 2147483647) . '.' . time();
}
$event_name = $_GET['event_name'] ?? '';
$event_name = is_string($event_name) ? str_replace(' ', '_', $event_name) : '';
if (!preg_match('/^[A-Za-z][A-Za-z0-9_]{0,39}$/D', $event_name)) {
    $event_name = 'email_open';
}

$url = 'https://www.google-analytics.com/mp/collect?' . http_build_query([
    'measurement_id' => $measurement_id,
    'api_secret' => $api_secret,
]);
$event = [
    'client_id' => $client_id,
    'events' => [[
        'name' => $event_name,
        'params' => ['engagement_time_msec' => 1, 'session_id' => time()],
    ]],
];
$request = curl_init($url);
curl_setopt_array($request, [
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => json_encode($event),
    CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_CONNECTTIMEOUT => 2,
    CURLOPT_TIMEOUT => 5,
]);
curl_exec($request);
$status = curl_getinfo($request, CURLINFO_HTTP_CODE);
if ($status < 200 || $status >= 300) {
    error_log('Email tracking could not send the GA4 event. HTTP status: ' . $status);
}
curl_close($request);
"""
