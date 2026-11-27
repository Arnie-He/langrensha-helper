# -*- coding: utf-8 -*-
"""语音播报用到的全部台词。

每一条对应 public/audio/<id>.m4a。改了文字以后运行 tools/gen_audio.py 重新生成音频。
"""

_NUM = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
        '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八']

CLIPS = {
    'test': '这是播报试音，请把音量调大，让所有人都能听到',
    'deal': '请大家查看自己的身份牌',

    'night_fall': '天黑请闭眼',
    'day_break': '天亮了，请大家睁眼',

    # ---- 夜晚各环节：睁眼 / 操作提示 / 闭眼
    'mixed_open': '混血儿请睁眼',
    'mixed_prompt': '请选择你的榜样',
    'mixed_close': '混血儿请闭眼',

    'cupid_open': '丘比特请睁眼',
    'cupid_prompt': '请选择两名玩家成为情侣',
    'cupid_close': '丘比特请闭眼',

    'lovers_open': '所有玩家请睁眼，看自己的手机',
    'lovers_prompt': '请确认自己有没有被选为情侣，看完请点确认',
    'lovers_close': '所有玩家请闭眼',

    'nightmare_open': '梦魇请睁眼',
    'nightmare_prompt': '请选择今晚要恐惧的玩家',
    'nightmare_close': '梦魇请闭眼',

    'magician_open': '魔术师请睁眼',
    'magician_prompt': '请选择今晚要交换的两名玩家',
    'magician_close': '魔术师请闭眼',

    'dreamer_open': '摄梦人请睁眼',
    'dreamer_prompt': '请选择今晚的梦游者',
    'dreamer_close': '摄梦人请闭眼',

    'guard_open': '守卫请睁眼',
    'guard_prompt': '请选择你今晚要守护的玩家',
    'guard_close': '守卫请闭眼',

    'mech_open': '机械狼请睁眼',
    'mech_prompt': '请选择要学习的玩家，或者使用你的技能',
    'mech_close': '机械狼请闭眼',

    'wolf_open': '狼人请睁眼',
    'wolf_prompt': '请确认你的同伴，并选择今晚要击杀的目标',
    'wolf_close': '狼人请闭眼',

    'beauty_open': '狼美人请睁眼',
    'beauty_prompt': '请选择今晚要魅惑的玩家',
    'beauty_close': '狼美人请闭眼',

    'gargoyle_open': '石像鬼请睁眼',
    'gargoyle_prompt': '请选择你要查验的玩家',
    'gargoyle_close': '石像鬼请闭眼',

    'witch_open': '女巫请睁眼',
    'witch_prompt': '今晚这位玩家倒牌了。你有一瓶解药，是否使用？你有一瓶毒药，是否使用？',
    'witch_close': '女巫请闭眼',

    'seer_open': '预言家请睁眼',
    'seer_prompt': '请选择你要查验的玩家',
    'seer_close': '预言家请闭眼',

    'psychic_open': '通灵师请睁眼',
    'psychic_prompt': '请选择你要查验的玩家',
    'psychic_close': '通灵师请闭眼',

    'gravekeeper_open': '守墓人请睁眼',
    'gravekeeper_prompt': '请查看昨天被放逐玩家的阵营',
    'gravekeeper_close': '守墓人请闭眼',

    'witcher_open': '猎魔人请睁眼',
    'witcher_prompt': '请选择今晚是否狩猎一名玩家',
    'witcher_close': '猎魔人请闭眼',

    'seal': '今晚所有神职的技能被封印',

    # ---- 警长竞选
    'elect_start': '现在开始警长竞选。想竞选警长的玩家，请在手机上选择上警',
    'elect_cands': '上警的玩家是',
    'elect_none': '没有玩家上警',
    'elect_speech': '请上警的玩家按手机上的顺序发言',
    'elect_withdraw': '现在是退水环节。上警的玩家，请在手机上选择是否退水',
    'elect_withdrawn': '玩家退水',
    'elect_no_withdraw': '没有玩家退水',
    'elect_vote': '请警下的玩家在手机上投票',
    'elect_vote_pk': '请警下和退水的玩家在手机上投票',
    'elect_win': '玩家当选警长',
    'elect_tie': '平票。请平票的玩家依次发言，然后警下和退水的玩家再投一轮',
    'elect_lost': '警徽流失，本局没有警长',
    'elect_postponed': '警长竞选推迟到明天',
    'badge_pass': '玩家把警徽移交给',
    'badge_tear': '玩家撕掉了警徽',
    'order_ask': '请警长在手机上选择发言顺序',

    # ---- 白天
    'peaceful': '昨夜是平安夜',
    'died_last_night': '昨夜倒牌的玩家是',
    'settle_ask': '请出局的玩家查看手机，并完成确认',
    'shoot': '玩家发动技能，带走了',
    'follow_die': '玩家随之出局',
    'last_words': '玩家请发表遗言',
    'discuss': '请开始发言',

    'vote_start': '请大家在手机上投票',
    'exiled': '玩家被放逐出局',
    'vote_tie': '平票。请平票玩家依次发言，然后再次投票',
    'vote_tie_none': '再次平票，今天无人出局',
    'vote_none': '无人得票，今天无人出局',
    'idiot_flip': '玩家翻牌白痴，免于放逐',

    'boom': '玩家自爆',
    'take': '带走了',
    'to_night': '直接进入黑夜',
    'duel_a': '玩家翻牌骑士，向',
    'duel_b': '玩家发起决斗',
    'duel_win': '决斗成功，对方是狼人，直接进入黑夜',
    'duel_lose': '决斗失败，对方是好人，骑士出局',
    'bm_delay': '玩家翻牌血月使徒，将在明天天亮后出局',
    'bm_die': '玩家是血月使徒，现在出局',

    'win_good': '游戏结束，好人阵营获胜',
    'win_wolf': '游戏结束，狼人阵营获胜',
    'win_third': '游戏结束，情侣阵营获胜',
}

for _i in range(1, 19):
    CLIPS['n%d' % _i] = _NUM[_i] + '号'


def cue_text(clips):
    """把一串片段拼成一句字幕。"""
    out = []
    for c in clips:
        if c.startswith('n') and c[1:].isdigit():
            out.append('%s号' % c[1:])
        else:
            out.append(CLIPS.get(c, ''))
    return ' '.join(out)
