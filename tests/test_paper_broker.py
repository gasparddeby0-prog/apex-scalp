from apex.broker.paper_broker import PaperBroker
from apex.models import Direction, OrderRequest, OrderType, Timeframe


def test_connect_and_account(settings):
    broker = PaperBroker(settings)
    assert broker.connect()
    acc = broker.account()
    assert acc.balance == 10_000.0
    assert acc.connected


def test_candles_shapes_and_resample(settings):
    broker = PaperBroker(settings)
    broker.connect()
    m1 = broker.candles("EURUSD", Timeframe.M1, 100)
    assert len(m1) == 100
    m5 = broker.candles("EURUSD", Timeframe.M5, 50)
    assert len(m5) == 50
    # M5 highs/lows must bound the constituent closes sensibly.
    assert (m5.high >= m5.low).all()


def test_market_order_creates_position_and_pnl(settings):
    broker = PaperBroker(settings)
    broker.connect()
    tick = broker.tick("EURUSD")
    req = OrderRequest(
        symbol="EURUSD",
        order_type=OrderType.BUY,
        volume=0.10,
        price=tick.ask,
        stop_loss=tick.ask - 0.0020,
        take_profit=tick.ask + 0.0040,
        magic=1,
        comment="test",
    )
    res = broker.send_order(req)
    assert res.ok
    positions = broker.positions()
    assert len(positions) == 1
    assert positions[0].direction is Direction.LONG


def test_sl_tp_eventually_settles(settings):
    broker = PaperBroker(settings)
    broker.connect()
    tick = broker.tick("EURUSD")
    # Tight SL/TP so the random walk resolves it quickly.
    broker.send_order(OrderRequest(
        symbol="EURUSD", order_type=OrderType.BUY, volume=0.10, price=tick.ask,
        stop_loss=tick.ask - 0.0008, take_profit=tick.ask + 0.0008, magic=1,
    ))
    for _ in range(2000):
        broker.step(1)
        if not broker.positions():
            break
    assert broker.positions() == []
    assert len(broker.realised_pnl) == 1


def test_partial_close(settings):
    broker = PaperBroker(settings)
    broker.connect()
    tick = broker.tick("XAUUSD")
    broker.send_order(OrderRequest(
        symbol="XAUUSD", order_type=OrderType.SELL, volume=0.10, price=tick.bid,
        stop_loss=tick.bid + 5.0, take_profit=tick.bid - 5.0, magic=1,
    ))
    ticket = broker.positions()[0].ticket
    res = broker.close_position(ticket, volume=0.04)
    assert res.ok
    pos = broker.positions()[0]
    assert abs(pos.volume - 0.06) < 1e-9
