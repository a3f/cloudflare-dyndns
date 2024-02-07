import os
import CloudFlare
import waitress
import flask
import socket
import requests


app = flask.Flask(__name__)


@app.route('/', methods=['GET'])
def main():
    token = flask.request.args.get('token')
    zone = flask.request.args.get('zone')
    record = flask.request.args.get('record')
    ipv4 = flask.request.args.get('ipv4')
    ipv6 = flask.request.args.get('ipv6')

    if not token:
        try:
            with open('/run/secrets/token') as f:
                token = f.read()
        except FileNotFoundError:
            pass

    if not token:
        return flask.jsonify({'status': 'error', 'message': 'Missing token URL parameter.'}), 400
    if not zone:
        return flask.jsonify({'status': 'error', 'message': 'Missing zone URL parameter.'}), 400
    if not ipv4 and not ipv6:
        return flask.jsonify({'status': 'error', 'message': 'Missing ipv4 or ipv6 URL parameter.'}), 400

    cf = CloudFlare.CloudFlare(token=token)
    try:
        zones = cf.zones.get(params={'name': zone})

        if not zones:
            return flask.jsonify({'status': 'error', 'message': 'Zone {} does not exist.'.format(zone)}), 404

        record_zone_concat = '{}.{}'.format(record, zone) if record is not None else zone

        a_record = cf.zones.dns_records.get(zones[0]['id'], params={
                                            'name': record_zone_concat, 'match': 'all', 'type': 'A'})
        aaaa_record = cf.zones.dns_records.get(zones[0]['id'], params={
                                            'name': record_zone_concat, 'match': 'all', 'type': 'AAAA'})

        if ipv4 is not None and not a_record:
            return flask.jsonify({'status': 'error', 'message': f'A record for {record_zone_concat} does not exist.'}), 404

        if ipv6 is not None and not aaaa_record:
            return flask.jsonify({'status': 'error', 'message': f'AAAA record for {record_zone_concat} does not exist.'}), 404

        if ipv4 is not None and a_record[0]['content'] != ipv4:
            cf.zones.dns_records.put(zones[0]['id'], a_record[0]['id'], data={
                                     'name': a_record[0]['name'], 'type': 'A', 'content': ipv4, 'proxied': a_record[0]['proxied'], 'ttl': a_record[0]['ttl']})

        if ipv6 is not None and aaaa_record[0]['content'] != ipv6:
            cf.zones.dns_records.put(zones[0]['id'], aaaa_record[0]['id'], data={
                                     'name': aaaa_record[0]['name'], 'type': 'AAAA', 'content': ipv6, 'proxied': aaaa_record[0]['proxied'], 'ttl': aaaa_record[0]['ttl']})
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        return flask.jsonify({'status': 'error', 'message': str(e)}), 500

    return flask.jsonify({'status': 'success', 'message': 'Update successful.'}), 200

def inconsistent_ip(host, actual, expect):
    return flask.jsonify({'status': 'error',
                          'host': host,
                          'message': 'inconsistent IP addresses',
                          'addrs': { "actual": actual, "expect": expect }}), 500

@app.route('/healthz', methods=['GET'])
def healthz():
    ipv4 = flask.request.args.get('ipv4')
    ipv6 = flask.request.args.get('ipv6')

    if ipv4 is None and ipv6 is None:
        return flask.jsonify({'status': 'success', 'message': 'OK'}), 200

    zone = flask.request.args.get('zone')
    record = flask.request.args.get('record')

    if not zone:
        return flask.jsonify({'status': 'error', 'message': 'Missing zone URL parameter.'}), 400

    record_zone_concat = '{}.{}'.format(record, zone) if record is not None else zone


    if ipv4 == "":
        ipv4 = requests.get('https://api.ipify.org/').text
    if ipv6 == "":
        ipv6 = requests.get('https://api6.ipify.org/').text

    try:
        data = socket.getaddrinfo(record_zone_concat, None)
    except socket.gaierror as e:
        return flask.jsonify({'status': 'error', 'message': e.args[1]}), 500

    got_ipv4 = got_ipv6 = False

    for addr in data:
        (family, typ, proto, canonname, sockaddr) = addr
        if family == socket.AF_INET:
            actual = ipv4
            got_ipv4 = True
        elif family == socket.AF_INET6:
            actual = ipv6
            got_ipv6 = True
        else:
            continue

        if actual and sockaddr[0] != actual:
            return inconsistent_ip(record_zone_concat, actual, sockaddr[0])

    if ipv4 and not got_ipv4:
        return inconsistent_ip(record_zone_concat, ipv4, None)
    if ipv6 and not got_ipv6:
        return inconsistent_ip(record_zone_concat, ipv6, None)

    response = {'status': 'success', 'message': 'OK'}
    if ipv4:
        response['ipv4'] = ipv4
    if ipv6:
        response['ipv6'] = ipv6

    return flask.jsonify(response), 200

app.secret_key = os.urandom(24)
waitress.serve(app, host='0.0.0.0', port=80)
