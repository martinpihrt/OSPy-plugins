"""Helpers for Shelly Pro 3EM and Shelly 3EM Gen3 status payloads."""


def parse_three_phase_meter(response_data, cloud=False):
    """Return normalized three-phase values from Shelly.GetStatus data."""
    if cloud:
        data = response_data.get('data', {})
        status = data.get('device_status', {})
        online = bool(data.get('online', False))
    else:
        status = response_data
        online = True

    em = status.get('em:0')
    if not isinstance(em, dict):
        raise ValueError('Shelly status does not contain em:0')
    emdata = status.get('emdata:0', {})

    powers = [em.get('{}_act_power'.format(phase)) for phase in ('a', 'b', 'c')]
    voltages = [em.get('{}_voltage'.format(phase)) for phase in ('a', 'b', 'c')]
    currents = [em.get('{}_current'.format(phase)) for phase in ('a', 'b', 'c')]
    power_factors = [em.get('{}_pf'.format(phase)) for phase in ('a', 'b', 'c')]
    energy_wh = [emdata.get('{}_total_act_energy'.format(phase), 0) for phase in ('a', 'b', 'c')]
    returned_energy_wh = [emdata.get('{}_total_act_ret_energy'.format(phase), 0) for phase in ('a', 'b', 'c')]

    temperature = None
    temperature_status = status.get('temperature:0')
    if isinstance(temperature_status, dict):
        temperature = temperature_status.get('tC')

    network = status.get('wifi', {})
    if not isinstance(network, dict):
        network = {}
    ip_address = network.get('sta_ip', '')
    rssi = network.get('rssi')
    if not ip_address:
        ethernet = status.get('eth', {})
        if isinstance(ethernet, dict):
            ip_address = ethernet.get('ip', '')

    return {
        'online': online,
        'powers': powers,
        'reverse_powers': [-value if isinstance(value, (int, float)) and value < 0 else 0 for value in powers],
        'voltages': voltages,
        'currents': currents,
        'power_factors': power_factors,
        'energy_kwh': [value / 1000.0 if isinstance(value, (int, float)) else 0 for value in energy_wh],
        'returned_energy_kwh': [value / 1000.0 if isinstance(value, (int, float)) else 0 for value in returned_energy_wh],
        'total_power': em.get('total_act_power', sum(value for value in powers if isinstance(value, (int, float)))),
        'total_energy': sum(value for value in energy_wh if isinstance(value, (int, float))) / 1000.0,
        'total_returned_energy': sum(value for value in returned_energy_wh if isinstance(value, (int, float))) / 1000.0,
        'temperature': temperature,
        'ip': ip_address,
        'rssi': rssi,
    }
