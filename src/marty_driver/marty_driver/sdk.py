"""MartyPy lifecycle boundary, including cleanup when its handshake fails."""


def open_marty(method, locator, rate_hz, baud, port):
    from martypy import Marty

    # Retain the object before __init__: the SDK opens a transport before start()
    # can fail, so calling Marty(...) alone would lose access to cleanup on error.
    sdk = Marty.__new__(Marty)
    try:
        sdk.__init__(
            method, locator, blocking=False, subscribeRateHz=rate_hz,
            serialBaud=baud, port=port,
        )
        info = sdk.get_system_info()
        if info.get('rslt') != 'ok' or info.get('SystemName') != 'RIC':
            raise RuntimeError('The endpoint did not identify as a Marty RIC controller')
        return sdk
    except Exception:
        if getattr(sdk, 'client', None) is not None:
            sdk.close()
        raise
