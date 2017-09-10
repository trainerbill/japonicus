#!/usr/bin/env python
# -*- coding: utf-8 -*-

import random
import datetime
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.finance as mpf
from matplotlib import ticker
import matplotlib.dates as mdates
from gekkoWrapper import getAvailableDataset, runBacktest, getCandles
#from plotInfo import plotEvolutionSummary
import js2py
from bayes_opt import BayesianOptimization
from multiprocessing import Pool
import multiprocessing as mp


def moving_average(x, n, type='simple'):
    """
    compute an n period moving average.

    type is 'simple' | 'exponential'

    """
    x = np.asarray(x)
    if type == 'simple':
        weights = np.ones(n)
    else:
        weights = np.exp(np.linspace(-1., 0., n))

    weights /= weights.sum()

    a = np.convolve(x, weights, mode='full')[:len(x)]
    a[:n] = a[n]
    return a


def relative_strength(prices, n=14):
    """
    compute the n period relative strength indicator
    http://stockcharts.com/school/doku.php?id=chart_school:glossary_r#relativestrengthindex
    http://www.investopedia.com/terms/r/rsi.asp
    """

    deltas = np.diff(prices)
    seed = deltas[:n+1]
    up = seed[seed >= 0].sum()/n
    down = -seed[seed < 0].sum()/n
    rs = up/down
    rsi = np.zeros_like(prices)
    rsi[:n] = 100. - 100./(1. + rs)

    for i in range(n, len(prices)):
        delta = deltas[i - 1]  # cause the diff is 1 shorter

        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta

        up = (up*(n - 1) + upval)/n
        down = (down*(n - 1) + downval)/n

        rs = up/down
        rsi[i] = 100. - 100./(1. + rs)

    return rsi


def moving_average_convergence(x, nslow=26, nfast=12):
    """
    compute the MACD (Moving Average Convergence/Divergence) using a fast and slow exponential moving avg'
    return value is emaslow, emafast, macd which are len(x) arrays
    """
    emaslow = moving_average(x, nslow, type='exponential')
    emafast = moving_average(x, nfast, type='exponential')
    return emaslow, emafast, emafast - emaslow

def reconstructTradeSettingsDict(IND, Strategy):
    f = {
        "short": lambda x: x//5+1,
        "long": lambda x: x//3+10,
        "signal": lambda x: x//10+5,
        "interval": lambda x: x//3,
        "down": lambda x: (x//1.5-50)/40,
        "up": lambda x: (x//1.5-5)/40,
        "low": lambda x: x//2+10,
        "high": lambda x: x//2+45,
        "persistence": lambda x: x//25+1,
        "fibonacci": lambda x: (x//11+1)/10
    }
    Settings = {}
    Settings[Strategy] = {}
    Settings[Strategy]["thresholds"] = {}
    for key in "short long signal interval".split(" "):
        if key in IND:
            #Settings[Strategy][key] = f[key](IND[key])
            Settings[Strategy][key] = IND[key]
    for key in "down up low high persistence fibonacci".split(" "):
        if key in IND:
            #Settings[Strategy]["thresholds"][key] = f[key](IND[key])
            Settings[Strategy]["thresholds"][key] = IND[key]
    return Settings

def reconstructTradeSettings(IND, Strategy):
    Settings = {
        Strategy:{
            "short": IND[0]//5+1,
            "long": IND[1]//3+10,
            "signal": IND[2]//10+5,
            "interval": IND[3]//3,
            "thresholds": {
                "down": (IND[4]//1.5-50)/40,
                "up": (IND[5]//1.5-5)/40,
                "low": IND[6]//2+10,
                "high": IND[7]//2+45,
                "persistence": IND[8]//25+1,
                "fibonacci": (IND[9]//11+1)/10
            }
        }
    }
        
    return Settings

def getRandomDateRange(Limits, deltaDays=3):
    DateFormat="%Y-%m-%d %H:%M:%S"

    epochToString = lambda D: datetime.datetime.utcfromtimestamp(D).strftime(DateFormat)
    FLms = Limits['from']
    TLms = Limits['to']
    deltams=deltaDays * 24 * 60 * 60
    testms=testDays * 24 * 60 * 60

    Starting= random.randint(FLms,TLms-deltams-testms)
    DateRange = {
        "from": "%s" % epochToString(Starting),
        "to": "%s" % epochToString(Starting+deltams)
    }
    return DateRange
def getDateRange(Limits, deltaDays=3):
    DateFormat="%Y-%m-%d %H:%M:%S"

    epochToString = lambda D: datetime.datetime.utcfromtimestamp(D).strftime(DateFormat)
    deltams=deltaDays * 24 * 60 * 60

    DateRange = {
        "from": "%s" % epochToString(Limits['to']-deltams),
        "to": "%s" % epochToString(Limits['to'])
    }
    return DateRange

def evaluate_random(i):
    chosenRange = getAvailableDataset()
    DateRange = getRandomDateRange(chosenRange, deltaDays=deltaDays)
    return Evaluate(DateRange, params, Strategy)

def Evaluate(DateRange, Individual, Strategy):
    Settings = reconstructTradeSettingsDict(Individual, Strategy)
    #print(Settings)
    Score = runBacktest(Settings, DateRange)
    return Score

def gekko_search(**args):
    params.update(args.copy())
    if parallel:
        p = Pool(mp.cpu_count())
        scores = p.imap_unordered(evaluate_random, list(range(num_rounds)), 5)
        p.close()
    else:
        scores = [evaluate_random(n) for n in range(num_rounds)]
    series = pd.Series(scores)
    mean = series.mean()
    stats.append([series.count(), mean, series.std(), series.min()] +
         [series.quantile(x) for x in percentiles] + [series.max()])
    #for i in range(len(stats[-1])):
    #    print('// %s: %.3f' % (stats_index[i], stats[-1][i]))
    all_val.append(mean)
    return mean

def candlechart(ohlc, width=0.8):
    fig, ax = plt.subplots()
    mpf.candlestick2_ohlc(ax, opens=ohlc.open.values, closes=ohlc.close.values,
                          lows=ohlc.low.values, highs=ohlc.high.values,
                          width=width, colorup='r', colordown='b')

    xdate = ohlc.index
    ax.xaxis.set_major_locator(ticker.MaxNLocator(6))

    def mydate(x, pos):
        try:
            return xdate[int(x)]
        except IndexError:
            return ''

    ax.xaxis.set_major_formatter(ticker.FuncFormatter(mydate))
    ax.format_xdata = mdates.DateFormatter('%Y-%m-%d')
    ax.grid()

    fig.autofmt_xdate()
    fig.tight_layout()

    return fig, ax

def showCandles():
    chosenRange = getAvailableDataset()
    DateRange = getDateRange(chosenRange["to"], deltaDays=deltaDays)
    print("\t%s to %s" % (DateRange['from'], DateRange['to']))
    candle = getCandles(DateRange)
    df = pd.DataFrame(candle)
    df["start"] = pd.to_datetime(df["start"], unit='s')
    df.index = df["start"]
    fig, ax = candlechart(df)
    fig.show()
    plt.waitforbuttonpress()
    exit()

def flatten_dict(d):
    def items():
        for key, value in d.items():
            if isinstance(value, dict):
                for subkey, subvalue in flatten_dict(value).items():
                    #yield key + "." + subkey, subvalue
                    yield subkey, subvalue
            else:
                yield key, value

    return dict(items())

if __name__ == '__main__':
    MODES = ['MACD', 'DEMA', 'RSI', 'PPO']
    Strategy = MODES[0]
    percentiles = np.array([0.25, 0.5, 0.75])
    formatted_percentiles = [str(int(round(x*100)))+"%" for x in percentiles]
    stats_index = (['count', 'mean', 'std', 'min'] +
              formatted_percentiles + ['max'])

    filename = "example-config.js"
    with open(filename, "r") as f:
        text = f.read()
    text = text.replace("module.exports = config;","config;")
    config = js2py.eval_js(text).to_dict()
    #print(config)

    deltaDays = 3
    testDays = 3
    num_rounds = 10
    random_state = 2017
    num_iter = 45
    init_points = 9
    parallel = False
    all_val = []
    stats = []

    params = flatten_dict(config[Strategy])
    print("")
    print("Starting search %s parameters" % Strategy)
    #print(params)

    bo = BayesianOptimization(gekko_search, {
            "short": (1,30),
            "long": (1,30),
            "signal": (5,10),
            "interval": (3,15),
            "down": (-0.025,0.025),
            "up": (-0.025,0.025),
            "low": (3,30),
            "high": (45,70),
            "fibonacci": (0.1, 0.2)
        })

    # 1st Evaluate
    bo.maximize(init_points=init_points, n_iter=num_iter)

    max_val = bo.res['max']['max_val']
    index = all_val.index(max_val)
    s1 = stats[index]
    # 2nd Evaluate
    chosenRange = getAvailableDataset()
    DateRange = getDateRange(chosenRange, deltaDays=testDays)
    max_params = bo.res['max']['max_params'].copy()
    max_params["persistence"] = 1
    gekko_search(**max_params)
    s2 = stats[-1]
    # 3rd Evaluate
    score = Evaluate(DateRange, max_params, Strategy)
    resultjson = reconstructTradeSettingsDict(max_params, Strategy)[Strategy]

    # config.js like output
    print("")
    print("// "+'-'*50)
    print("// "+Strategy + ' Settings')
    #print("// "+'-'*50)
    #print(json.dumps(bo.res, indent=2))
    print("// "+'-'*50)
    print("// 1st Evaluate:")
    for i in range(len(s1)):
        print('// %s: %.3f' % (stats_index[i], s1[i]))
    print("// "+'-'*50)
    print("// 2nd Evaluate:")
    for i in range(len(s2)):
        print('// %s: %.3f' % (stats_index[i], s2[i]))
    print("// "+'-'*50)
    print("// 3rd Evaluate nearest date: %s to %s" % (DateRange['from'], DateRange['to']))
    print("// Evaluted Score: %f" % score)
    print("// "+'-'*50)
    print("config.%s = {%s}" % (Strategy, json.dumps(resultjson, indent=2)[1:-1]))
    print("// "+'-'*50)



