"""Live dashboard built with Dash + Plotly.

Renders the five panels from the spec - account, open positions, pending
signals, statistics and system logs - plus a candlestick chart. In paper mode
the dashboard also *drives* the simulation: every refresh it advances the
synthetic market and runs one scan cycle, so you can watch the bot work end to
end without any external terminal.
"""

from __future__ import annotations

import plotly.graph_objects as go
from dash import (
    Dash,
    Input,
    Output,
    callback_context,  # noqa: F401  (kept for clarity / future use)
    dash_table,
    dcc,
    html,
)

from apex.broker.paper_broker import PaperBroker
from apex.engine.orchestrator import Orchestrator
from apex.logging_setup import recent_logs
from apex.models import Timeframe
from apex.stats import compute_stats

_CARD = {
    "background": "#11151c",
    "border": "1px solid #232a35",
    "borderRadius": "8px",
    "padding": "12px 16px",
    "margin": "6px",
    "flex": "1",
    "minWidth": "160px",
}
_PANEL = {
    "background": "#0d1117",
    "border": "1px solid #232a35",
    "borderRadius": "8px",
    "padding": "12px 16px",
    "margin": "8px",
}
_LABEL = {"color": "#7d8794", "fontSize": "12px", "textTransform": "uppercase"}
_VALUE = {"color": "#e6edf3", "fontSize": "22px", "fontWeight": "600"}


def build_app(orchestrator: Orchestrator, chart_symbol: str | None = None,
              step_bars: int = 5) -> Dash:
    """Create the Dash app bound to a running :class:`Orchestrator`."""
    app = Dash(__name__, title="APEX-SCALP")
    symbol = chart_symbol or orchestrator.settings.symbols[0]
    is_paper = isinstance(orchestrator.broker, PaperBroker)

    app.layout = html.Div(
        style={"background": "#010409", "minHeight": "100vh", "fontFamily": "monospace",
               "padding": "10px"},
        children=[
            html.Div(
                style={"display": "flex", "justifyContent": "space-between",
                       "alignItems": "center", "margin": "4px 10px"},
                children=[
                    html.H2("APEX-SCALP", style={"color": "#58a6ff", "margin": 0}),
                    html.Div(
                        f"{orchestrator.settings.mode.value.upper()} MODE"
                        + ("  (simulation driving)" if is_paper else ""),
                        style={"color": "#d29922", "fontWeight": "600"},
                    ),
                ],
            ),
            dcc.Interval(id="tick", interval=1000, n_intervals=0),
            html.Div(id="account-cards", style={"display": "flex", "flexWrap": "wrap"}),
            html.Div(
                style={"display": "flex", "flexWrap": "wrap"},
                children=[
                    html.Div(style={**_PANEL, "flex": "2", "minWidth": "480px"}, children=[
                        html.Div("CHART", style=_LABEL),
                        dcc.Graph(id="chart", config={"displayModeBar": False},
                                  style={"height": "340px"}),
                    ]),
                    html.Div(style={**_PANEL, "flex": "1", "minWidth": "320px"}, children=[
                        html.Div("STATISTIQUES", style=_LABEL),
                        html.Div(id="stats"),
                    ]),
                ],
            ),
            html.Div(style=_PANEL, children=[
                html.Div("POSITIONS OUVERTES", style=_LABEL),
                html.Div(id="positions"),
            ]),
            html.Div(style=_PANEL, children=[
                html.Div("SIGNAUX EN ATTENTE", style=_LABEL),
                html.Div(id="signals"),
            ]),
            html.Div(style=_PANEL, children=[
                html.Div("LOGS SYSTÈME", style=_LABEL),
                html.Pre(id="logs", style={"color": "#8b949e", "maxHeight": "200px",
                                           "overflowY": "auto", "fontSize": "12px"}),
            ]),
        ],
    )

    @app.callback(
        Output("account-cards", "children"),
        Output("chart", "figure"),
        Output("stats", "children"),
        Output("positions", "children"),
        Output("signals", "children"),
        Output("logs", "children"),
        Input("tick", "n_intervals"),
    )
    def refresh(_n):
        # In paper mode, advance the market and run one cycle each refresh.
        if is_paper:
            orchestrator.broker.step(step_bars)
        result = orchestrator.run_once(execute=True)

        acc = result.account
        dd = orchestrator.risk.drawdown_pct(acc)
        cards = [
            _card("Balance", f"{acc.balance:,.2f}"),
            _card("Equity", f"{acc.equity:,.2f}"),
            _card("Free margin", f"{acc.free_margin:,.2f}"),
            _card("Drawdown", f"{dd:.2f}%", color="#f85149" if dd >= 5 else "#3fb950"),
            _card("Open", str(len(orchestrator.broker.positions()))),
        ]

        fig = _chart_figure(orchestrator, symbol)
        stats = _stats_block(orchestrator)
        positions = _positions_table(orchestrator)
        signals = _signals_table(result)
        logs = _logs_text()
        return cards, fig, stats, positions, signals, logs

    return app


# ── Render helpers ───────────────────────────────────────────────────────────────
def _card(label: str, value: str, color: str = "#e6edf3"):
    return html.Div(style=_CARD, children=[
        html.Div(label, style=_LABEL),
        html.Div(value, style={**_VALUE, "color": color}),
    ])


def _chart_figure(orch: Orchestrator, symbol: str) -> go.Figure:
    fig = go.Figure()
    try:
        candles = orch.broker.candles(symbol, Timeframe.M5, 120)
        if len(candles) > 0:
            fig.add_trace(go.Candlestick(
                x=list(candles.time), open=candles.open, high=candles.high,
                low=candles.low, close=candles.close, name=symbol,
            ))
    except Exception:  # pragma: no cover - chart is best-effort
        pass
    fig.update_layout(
        template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
        xaxis_rangeslider_visible=False, title=dict(text=f"{symbol} M5", x=0.01),
    )
    return fig


def _stats_block(orch: Orchestrator):
    pnls = getattr(orch.broker, "realised_pnl", [])
    s = compute_stats(pnls)
    pf = "inf" if s.profit_factor == float("inf") else f"{s.profit_factor:.2f}"
    rows = [
        ("Trades", str(s.trades)),
        ("Win rate", f"{s.win_rate:.1f}%"),
        ("Profit factor", pf),
        ("Total PnL", f"{s.total_pnl:,.2f}"),
        ("Expectancy", f"{s.expectancy:,.2f}"),
        ("Sharpe (per-trade)", f"{s.sharpe:.2f}"),
        ("Max DD", f"{s.max_drawdown:,.2f}"),
        ("Streak W/L", f"{s.best_streak}/{s.worst_streak}"),
    ]
    return html.Table(
        style={"width": "100%", "color": "#e6edf3", "borderCollapse": "collapse"},
        children=[html.Tr([
            html.Td(k, style={"color": "#7d8794", "padding": "3px 0"}),
            html.Td(v, style={"textAlign": "right", "fontWeight": "600"}),
        ]) for k, v in rows],
    )


def _positions_table(orch: Orchestrator):
    rows = []
    for p in orch.broker.positions():
        rows.append({
            "Ticket": p.ticket, "Symbol": p.symbol, "Dir": p.direction.value,
            "Lots": f"{p.volume:.2f}", "Entry": f"{p.entry_price:.5f}",
            "SL": f"{p.stop_loss:.5f}", "TP": f"{p.take_profit:.5f}",
            "PnL": f"{p.profit:.2f}", "Comment": p.comment,
        })
    return _table(rows, "No open positions.")


def _signals_table(result):
    rows = []
    for plan in sorted(result.plans, key=lambda p: p.score, reverse=True):
        if plan.direction.value == "NONE" and plan.score == 0:
            continue
        rows.append({
            "Symbol": plan.symbol, "Dir": plan.direction.value,
            "Score": f"{plan.score:.1f}", "Strategies": "+".join(plan.strategy_ids),
            "Decision": plan.decision, "Entry": f"{plan.entry:.5f}" if plan.entry else "-",
            "SL": f"{plan.stop_loss:.5f}" if plan.stop_loss else "-",
            "Lots": f"{plan.volume:.2f}", "Notes": "; ".join(plan.notes)[:60],
        })
    return _table(rows, "No active signals this cycle.")


def _table(rows: list[dict], empty: str):
    if not rows:
        return html.Div(empty, style={"color": "#7d8794", "padding": "8px 0"})
    return dash_table.DataTable(
        data=rows,
        columns=[{"name": k, "id": k} for k in rows[0]],
        style_table={"overflowX": "auto"},
        style_header={"backgroundColor": "#161b22", "color": "#58a6ff",
                      "fontWeight": "600", "border": "none"},
        style_cell={"backgroundColor": "#0d1117", "color": "#e6edf3",
                    "border": "1px solid #161b22", "fontFamily": "monospace",
                    "fontSize": "12px", "padding": "6px"},
    )


def _logs_text() -> str:
    lines = []
    for rec in recent_logs(40):
        lines.append(f"[{rec['time'].strftime('%H:%M:%S')}] {rec['level']:<5} "
                     f"{rec['name']} | {rec['message']}")
    return "\n".join(lines)


def run_dashboard(orchestrator: Orchestrator, host: str = "127.0.0.1", port: int = 8050,
                  debug: bool = False) -> None:
    app = build_app(orchestrator)
    app.run(host=host, port=port, debug=debug)
