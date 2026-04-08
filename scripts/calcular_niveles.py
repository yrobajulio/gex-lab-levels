import yfinance as yf
import numpy as np
import pandas as pd
from scipy.stats import norm
from datetime import datetime, date
import json
import os

MAG7 = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN', 'META', 'GOOGL']

TICKERS = [
    'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN', 'META', 'GOOGL',
    'SOFI', 'AMD', 'NFLX', 'COIN', 'PLTR', 'MSTR', 'HOOD',
    'UBER', 'SHOP', 'SQ', 'RBLX', 'SNAP', 'BABA'
]

def black_scholes_greeks_full(S, K, T, r, sigma, option_type='call'):
    if T <= 0 or sigma <= 0:
        return 0, 0, 0, 0
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vanna = -norm.pdf(d1) * d2 / sigma
    charm = -norm.pdf(d1) * (2*r*T - d2*sigma*np.sqrt(T)) / (2*T*sigma*np.sqrt(T))
    if option_type == 'call':
        delta = norm.cdf(d1)
    else:
        delta = norm.cdf(d1) - 1
        charm = -charm
    return delta, gamma, vanna, charm

def get_config(ticker_symbol, spot):
    if ticker_symbol in MAG7:
        return {'expiraciones': 5, 'rango': 0.10}
    else:
        if spot < 50:
            return {'expiraciones': 8, 'rango': 0.20}
        elif spot < 200:
            return {'expiraciones': 8, 'rango': 0.15}
        else:
            return {'expiraciones': 8, 'rango': 0.10}

def calcular_para_config(ticker, spot, expiraciones, rango, r=0.043):
    all_calls, all_puts = [], []
    for exp in expiraciones:
        try:
            chain = ticker.option_chain(exp)
            c = chain.calls.copy()
            p = chain.puts.copy()
            T = max((datetime.strptime(exp, '%Y-%m-%d') - datetime.now()).days / 365, 1/365)
            c[['delta','gamma','vanna','charm']] = c.apply(
                lambda row: black_scholes_greeks_full(spot, row['strike'], T, r, row['impliedVolatility'], 'call'),
                axis=1, result_type='expand')
            p[['delta','gamma','vanna','charm']] = p.apply(
                lambda row: black_scholes_greeks_full(spot, row['strike'], T, r, row['impliedVolatility'], 'put'),
                axis=1, result_type='expand')
            all_calls.append(c)
            all_puts.append(p)
        except Exception as e:
            print(f"Error en expiracion {exp}: {e}")
            continue
    if not all_calls:
        return None
    calls = pd.concat(all_calls)
    puts  = pd.concat(all_puts)
    calls['GEX'] = calls['openInterest'] * calls['gamma'] * spot * 100
    puts['GEX']  = -puts['openInterest'] * puts['gamma'] * spot * 100
    gex_calls = calls.groupby('strike')[['GEX']].sum()
    gex_puts  = puts.groupby('strike')[['GEX']].sum()
    combined  = gex_calls.add(gex_puts, fill_value=0).sort_index()
    rango_activo = combined[
        (combined.index >= spot*(1-rango)) &
        (combined.index <= spot*(1+rango))
    ].copy()
    if len(rango_activo) < 3:
        return None
    rango_activo['GEX_abs'] = rango_activo['GEX'].abs()
    ceiling_candidates = rango_activo[rango_activo.index > spot]
    floor_candidates   = rango_activo[rango_activo.index <= spot]
    positivos_arriba = ceiling_candidates[ceiling_candidates['GEX'] > 0]
    negativos_abajo  = floor_candidates[floor_candidates['GEX'] < 0]
    ceiling_strike = positivos_arriba['GEX'].idxmax() if len(positivos_arriba) > 0 else ceiling_candidates['GEX'].idxmax()
    floor_strike   = negativos_abajo['GEX'].idxmin()  if len(negativos_abajo)  > 0 else floor_candidates['GEX'].idxmin()
    entre        = rango_activo.loc[floor_strike:ceiling_strike]
    pivot_strike = entre['GEX_abs'].idxmin()
    mid_high = (pivot_strike + ceiling_strike) / 2
    mid_low  = (pivot_strike + floor_strike) / 2
    return {
        'ceiling':  float(ceiling_strike),
        'mid_high': round(float(mid_high), 2),
        'pivot':    round(float(pivot_strike), 2),
        'mid_low':  round(float(mid_low), 2),
        'floor':    float(floor_strike),
        'oi_calls': int(calls['openInterest'].sum()),
        'oi_puts':  int(puts['openInterest'].sum())
    }

def calcular_niveles(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        spot   = ticker.fast_info['last_price']
        if not ticker.options:
            return None
        config       = get_config(ticker_symbol, spot)
        hoy          = date.today().strftime('%Y-%m-%d')
        expiraciones = list(ticker.options[:config['expiraciones']])
        niveles      = calcular_para_config(ticker, spot, expiraciones, config['rango'])
        if not niveles:
            return None
        return {'ticker': ticker_symbol, 'spot': round(float(spot), 2), 'timestamp': hoy, 'niveles': niveles}
    except Exception as e:
        print(f"Error con {ticker_symbol}: {e}")
        return None

def generar_pine_script(ticker_symbol, niveles):
    n = niveles
    return f"//@version=5\nindicator(\'GEX Levels - {ticker_symbol}\', overlay=true)\nhline({n[\'ceiling\']}, \'Ceiling\', color.new(color.green, 0), linewidth=2)\nhline({n[\'mid_high\']}, \'Mid High\', color.new(color.yellow, 0), linewidth=1)\nhline({n[\'pivot\']}, \'Pivot\', color.new(color.white, 0), linewidth=2)\nhline({n[\'mid_low\']}, \'Mid Low\', color.new(color.yellow, 0), linewidth=1)\nhline({n[\'floor\']}, \'Floor\', color.new(color.red, 0), linewidth=2)"

if __name__ == '__main__':
    resultados = []
    for t in TICKERS:
        print(f"Calculando {t}...")
        resultado = calcular_niveles(t)
        if resultado:
            resultado['pine_script'] = generar_pine_script(t, resultado['niveles'])
            resultados.append(resultado)
    os.makedirs('data', exist_ok=True)
    with open('data/levels.json', 'w') as f:
        json.dump(resultados, f, indent=2)
    print(f"Done. {len(resultados)} tickers procesados.")
