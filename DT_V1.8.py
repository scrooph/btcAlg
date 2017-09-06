###
import numpy as np
import talib

# 可以仿照格式修改，基本都能运行。如果想了解详情请参考新手学堂的API文档。
PARAMS = {
    "start_time": "2017-09-01 00:00:00",  # 回测起始时间
    "end_time": "2017-09-04 21:00:00",  # 回测结束时间
    "commission": 0.002,  # 此处设置交易佣金
    "slippage": 0.001,  # 此处设置交易滑点
    "account_initial": {"huobi_cny_cash": 0,
                      "huobi_cny_ltc": 20},  # 设置账户初始状态
}

def initialize(context):
    # 设置回测频率, 可选："1m", "5m", "15m", "30m", "60m", "4h", "1d", "1w"
    context.frequency = "5m"
    # 设置回测基准, 比特币："huobi_cny_btc", 莱特币："huobi_cny_ltc", 以太坊："huobi_cny_eth"
    context.benchmark = "huobi_cny_ltc"
    # 设置回测标的, 比特币："huobi_cny_btc", 莱特币："huobi_cny_ltc", 以太坊："huobi_cny_eth"
    context.security = "huobi_cny_ltc"

    # 设置策略参数
    # 计算HH,HC,LC,LL所需的历史bar数目，用户自定义的变量，可以被handle_data使用;如果只需要看之前1根bar，则定义window_size=1
    context.user_data.window_size = 8
    context.user_data.atr_period = 8
    # 用户自定义的变量，可以被handle_data使用，触发多头的range
    context.user_data.K1 = 0.15
    context.user_data.K3 = 0.3
    # 用户自定义的变量，可以被handle_data使用，触发空头的range.当K1<K2时，多头相对容易被触发,当K1>K2时，空头相对容易被触发
    context.user_data.K2 = 0.8
    # 止损线，用户自定义的变量，可以被handle_data使用
    context.user_data.portfolio_stop_loss = 0.75
    # 用户自定义变量，记录下是否已经触发止损
    context.user_data.stop_loss_triggered = False
    # 止盈线，用户自定义的变量，可以被handle_data使用
    context.user_data.portfolio_stop_win = 2
    context.user_data.portfolio_stop_win_perday = 1.2
    # 用户自定义变量，记录下是否已经触发止盈
    context.user_data.stop_win_triggered = False
    context.user_data.hincome = 0
    context.user_data.hisprice = 0
    context.user_data.bakrate = 0.045
    context.user_data.hprice = 0
    context.user_data.hprice_list = []
    context.user_data.hdistance = 0
    context.user_data.cbrate = 0.05
    context.user_data.cbwidth = 50
    context.user_data.hpwidth = 16
    context.user_data.cbprice_list = []
    context.user_data.randlock = 0
    context.user_data.randlock_down = 0
    context.user_data.randlock_up = 0
    context.user_data.randlevel = 12
    context.user_data.cbdrop_width = 12
    context.user_data.cbdrop_lprice = 0
    context.user_data.cbdrop_range = 0.02
    context.user_data.range_ratio = 1.0
    context.user_data.period = 60
    context.user_data.over_sell = 70
    context.user_data.over_sell_fix = 75
    
    context.user_data.portfolio_cbrate = 0.08
    context.user_data.portfolio_bottom = 0.5
    context.user_data.portfolio_high = 0
    


# 阅读3，策略核心逻辑：
# handle_data函数定义了策略的执行逻辑，按照frequency生成的bar依次读取并执行策略逻辑，直至程序结束。
# handle_data和bar的详细说明，请参考新手学堂的解释文档。
def handle_data(context):
    # 若已触发止盈/止损线，不会有任何操作
    portfolio_rate = context.account.huobi_cny_net/context.account_initial.huobi_cny_net
    if portfolio_rate > context.user_data.portfolio_high:
        context.user_data.portfolio_high = portfolio_rate
    
    # 获取回看时间窗口内的历史数据
    hist4 = context.data.get_price(context.security, count=context.user_data.period, frequency=context.frequency)
    if len(hist4.index) < context.user_data.period:
        context.log.warn("bar的数量不足, 等待下一根bar...")
        return
    # 开盘价
    open_prices = np.array(hist4["open"])
    # 最高价
    high_prices = np.array(hist4["high"])
    # 最低价
    low_prices = np.array(hist4["low"])
    # 计算AR值
    ar = sum(high_prices - open_prices) / sum(open_prices - low_prices) * 100
    context.log.info("当前AR值为: %s" % ar)
    
    if portfolio_rate < (context.user_data.portfolio_high - context.user_data.portfolio_cbrate) and portfolio_rate > context.user_data.portfolio_bottom:
        if ar < context.user_data.over_sell:
            context.order.buy(context.security, cash_amount=str(context.account.huobi_cny_cash/6))
        else:
            context.order.sell(context.security, quantity=str(context.account.huobi_cny_ltc))
        return
    if portfolio_rate < context.user_data.portfolio_bottom:
        context.order.sell(context.security, quantity=str(context.account.huobi_cny_ltc))
        return

    # 获取历史数据, 取后window_size+1根bar
    hist = context.data.get_price(context.security, count=context.user_data.window_size + 1,
                                  frequency=context.frequency)
    # 判断读取数量是否正确
    if len(hist.index) < (context.user_data.window_size + 1):
        context.log.warn("bar的数量不足, 等待下一根bar...")
        return

    # 取得最近1 根 bar的close价格
    latest_close_price = context.data.get_current_price(context.security)

    # 开始计算N日最高价的最高价HH，N日收盘价的最高价HC，N日收盘价的最低价LC，N日最低价的最低价LL
    hh = np.max(hist["high"].iloc[-context.user_data.window_size-1:-1])
    hc = np.max(hist["close"].iloc[-context.user_data.window_size-1:-1])
    lc = np.min(hist["close"].iloc[-context.user_data.window_size-1:-1])
    ll = np.min(hist["low"].iloc[-context.user_data.window_size-1:-1])
    price_range = max(hh - lc, hc - ll)

    # 取得倒数第二根bar的close, 并计算上下界限
    up_bound = hist["open"].iloc[-1] + context.user_data.K1 * price_range
    low_bound = hist["open"].iloc[-1] - context.user_data.K2 * price_range

    context.log.info("当前 价格：%s, 上轨：%s, 下轨: %s" % (latest_close_price, up_bound, low_bound))
    #回撤价格
    
    #his_bound = context.user_data.hisprice*(1-context.user_data.cbrate)
    hist2 = context.data.get_price(context.security, count=context.user_data.cbwidth + 1,
                                  frequency=context.frequency)
    lpmax = np.max(hist2["high"].iloc[-context.user_data.cbwidth-1:-1])
    context.log.info("历史高点价格 %f" % lpmax )
    his_bound = lpmax*(1-context.user_data.cbrate)
    
    context.log.info("回撤价格 %f" % (his_bound) )
    
    if context.user_data.randlock:
        if context.user_data.randlock_up < context.user_data.randlevel and context.user_data.randlock_up <= context.user_data.randlock_down:
            if his_bound > latest_close_price:
                context.user_data.randlock_down = context.user_data.randlock_down + 1
            else:
                context.user_data.randlock_up = context.user_data.randlock_up + 1
            #AR 抄底
            if ar < context.user_data.over_sell:
                context.order.buy(context.security, cash_amount=str(context.account.huobi_cny_cash))
            else:
                context.log.info("AR值不够，暂时等待")
            if ar < context.user_data.over_sell_fix:
                context.order.buy(context.security, cash_amount=str(context.account.huobi_cny_cash/20))
            else:
                context.log.info("AR值不够75，暂时等待")
            return
        else:
            context.user_data.randlock_down = 0
            context.user_data.randlock_up = 0
            context.user_data.randlock = 0
        
    hist3 = context.data.get_price(context.security, count=context.user_data.atr_period + 1, frequency=context.frequency)
    if len(hist3.index) < context.user_data.atr_period + 1:
        context.log.warn("bar的数量不足, 等待下一根bar...")
        return
    # 收盘价
    close = np.array(hist3["close"])
    # 最高价
    high = np.array(hist3["high"])
    # 最低价
    low = np.array(hist3["low"])
    
    # 使用talib计算ATR
    try:
        # 获取最新的ATR值
        atr = talib.ATR(high, low, close, timeperiod=context.user_data.atr_period)[-1]
    except:
        context.log.error("计算ATR时出现错误...")
        return
    context.log.info("ATR VALUE %f"% atr)
    # 产生买入卖出信号，并执行操作
    if latest_close_price < his_bound and atr > 4.0:
        context.user_data.cbdrop_lprice = latest_close_price
        context.user_data.randlock = 1
        context.user_data.K1 = 0.15
        context.log.info("价格调整到回撤价格，产生卖出信号")
        account_mount = context.account.huobi_cny_ltc
        if account_mount >= HUOBI_CNY_LTC_MIN_ORDER_QUANTITY:
            # 卖出信号，且持有仓位，则市价单全仓卖出
            context.log.info("正在卖出 %s" % context.security)
            context.log.info("卖出数量为 %s" % account_mount)
            context.order.sell(context.security, quantity=str(account_mount))
        else:
            context.log.info("仓位不足，无法卖出")
    elif latest_close_price > up_bound:
        context.log.info("价格突破上轨，产生买入信号")
        context.user_data.K1 = 0.15
        if context.account.huobi_cny_cash >= HUOBI_CNY_LTC_MIN_ORDER_CASH_AMOUNT:
            # 买入信号，且持有现金，则市价单全仓买入
            context.log.info("正在买入 %s" % context.security)
            context.log.info("下单金额为 %s 元" % context.account.huobi_cny_cash)
            context.order.buy(context.security, cash_amount=str(context.account.huobi_cny_cash))
        else:
            context.log.info("现金不足，无法下单")
    elif latest_close_price < low_bound:
        context.log.info("价格突破下轨，产生卖出信号 %s %s" % (HUOBI_CNY_LTC_MIN_ORDER_QUANTITY, context.account.huobi_cny_ltc))
        if context.account.huobi_cny_ltc >= HUOBI_CNY_LTC_MIN_ORDER_QUANTITY:
            # 卖出信号，且持有仓位，则市价单全仓卖出
            context.log.info("正在卖出 %s" % context.security)
            context.log.info("卖出数量为 %s" % context.account.huobi_cny_ltc)
            context.order.sell(context.security, quantity=str(context.account.huobi_cny_ltc/3))
        else:
            context.log.info("仓位不足，无法卖出")
    else:
        context.log.info("无交易信号，进入下一根bar")
