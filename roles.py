# -*- coding: utf-8 -*-
"""角色表、常规板子、夜间顺序。

规则以网易《狼人杀》和线下赛事通行规则为准；各平台有出入的地方，
选了流传最广的一种，并在 README 里写明。
"""

# team: 阵营（seer 验出来的结果）   kind: 屠边时算哪一边
# pack: 夜里和其他狼人一起睁眼、互相认识、共同决定刀口
# boom: 能不能自爆
ROLES = {
    'wolf': {
        'name': '狼人', 'team': 'wolf', 'kind': 'wolf', 'pack': True, 'boom': True,
        'desc': '每晚和同伴一起睁眼，选一名玩家击杀。白天发言阶段可以在菜单里自爆，直接进入黑夜。'},
    'wolfking': {
        'name': '狼王', 'team': 'wolf', 'kind': 'wolf', 'pack': True, 'boom': True,
        'desc': '狼人阵营，每晚和狼人一起行动。被放逐或被刀时可以开枪带走一名玩家；被毒、自爆、殉情时不能开枪。'},
    'whitewolf': {
        'name': '白狼王', 'team': 'wolf', 'kind': 'wolf', 'pack': True, 'boom': True,
        'desc': '狼人阵营，每晚和狼人一起行动。白天自爆时可以带走一名玩家。'},
    'beauty': {
        'name': '狼美人', 'team': 'wolf', 'kind': 'wolf', 'pack': True, 'boom': False,
        'desc': '狼人阵营。每晚和狼人行动后，可以单独魅惑一名玩家（不能连续两晚魅惑同一人）。'
                '你出局时，最近被魅惑的人随你殉情；被骑士决斗出局时不会带走他。不能自爆，也不能被狼人自刀。'},
    'nightmare': {
        'name': '梦魇', 'team': 'wolf', 'kind': 'wolf', 'pack': True, 'boom': True,
        'desc': '狼人阵营。每晚最先睁眼，恐惧一名玩家，使他当晚无法使用技能（不能连续两晚恐惧同一人）。'
                '如果恐惧到狼人，当晚狼人无法袭击。第一夜恐惧时还不认识队友。'},
    'bloodmoon': {
        'name': '血月使徒', 'team': 'wolf', 'kind': 'wolf', 'pack': True, 'boom': True,
        'desc': '狼人阵营。自爆后的当晚，所有神职的技能被封印。'
                '如果你是最后一个狼人并被放逐，可以活到下一个天亮之后才出局。'},
    'ghostrider': {
        'name': '恶灵骑士', 'team': 'wolf', 'kind': 'wolf', 'pack': True, 'boom': False,
        'desc': '狼人阵营。夜里不会死亡（毒药无效，不能被自刀）。'
                '被预言家查验或被女巫下毒时，对方次日出局（整局只触发一次）。不能自爆。'},
    'gargoyle': {
        'name': '石像鬼', 'team': 'wolf', 'kind': 'wolf', 'pack': False, 'boom': False,
        'desc': '狼人阵营，但不和其他狼人见面，互相不认识。每晚可以查验一名玩家的具体身份。'
                '其他狼人全部出局后，由你在「狼人请睁眼」时刀人。不能自爆。'},
    'mech': {
        'name': '机械狼', 'team': 'wolf', 'kind': 'wolf', 'pack': False, 'boom': False,
        'desc': '狼人阵营，但不和其他狼人见面，互相不认识。整局可以学习一名玩家一次，得知他的身份并获得技能'
                '（通灵师：查验；女巫：一瓶毒药；守卫：守护；猎人：开枪；狼人：一次双刀）。'
                '学习之后被查验会显示成学到的身份。其他狼人全部出局后由你刀人。不能自爆。'},

    'villager': {
        'name': '村民', 'team': 'good', 'kind': 'villager',
        'desc': '没有特殊技能。靠发言和投票找出狼人。'},

    'seer': {
        'name': '预言家', 'team': 'good', 'kind': 'god',
        'desc': '每晚查验一名玩家，知道他是好人还是狼人。'},
    'witch': {
        'name': '女巫', 'team': 'good', 'kind': 'god',
        'desc': '有一瓶解药和一瓶毒药，各能用一次，同一晚不能都用。解药用掉以后，不再知道夜里谁倒牌。'},
    'hunter': {
        'name': '猎人', 'team': 'good', 'kind': 'god',
        'desc': '出局时可以开枪带走一名玩家；被毒、殉情时不能开枪。'},
    'guard': {
        'name': '守卫', 'team': 'good', 'kind': 'god',
        'desc': '每晚守护一名玩家不被狼人击杀，不能连续两晚守同一人。同时被守护又被解药救的人仍会倒牌。'},
    'idiot': {
        'name': '白痴', 'team': 'good', 'kind': 'god',
        'desc': '被投票放逐时翻牌免死，之后可以发言，但不能投票。'},
    'knight': {
        'name': '骑士', 'team': 'good', 'kind': 'god',
        'desc': '整局一次：白天发言阶段可以在菜单里翻牌，和一名玩家决斗。'
                '对方是狼人则他出局并立刻天黑；对方是好人则你出局。'},
    'psychic': {
        'name': '通灵师', 'team': 'good', 'kind': 'god',
        'desc': '每晚查验一名玩家，知道他的具体身份。'},
    'gravekeeper': {
        'name': '守墓人', 'team': 'good', 'kind': 'god',
        'desc': '从第二夜起，每晚得知前一天被放逐的玩家是好人还是狼人。'},
    'dreamer': {
        'name': '摄梦人', 'team': 'good', 'kind': 'god',
        'desc': '每晚必须选一名其他玩家成为梦游者，他当晚免疫狼刀和毒药。'
                '连续两晚让同一人梦游，他会死亡。如果你在夜里死亡，当晚的梦游者也会一起死亡。'},
    'magician': {
        'name': '魔术师', 'team': 'good', 'kind': 'god',
        'desc': '每晚可以交换两名玩家的号码牌，当晚所有对其中一人使用的技能都会落到另一人身上。'
                '每个号码整局只能被交换一次。'},
    'witcher': {
        'name': '猎魔人', 'team': 'good', 'kind': 'god',
        'desc': '从第二夜起，每晚可以狩猎一名玩家：他是狼人则他出局，他是好人则你出局。女巫的毒药对你无效。'},
    'cupid': {
        'name': '丘比特', 'team': 'good', 'kind': 'god',
        'desc': '第一夜指定两名玩家成为情侣（可以选自己），一人出局另一人殉情。'
                '情侣一好一狼时，情侣和你组成第三方阵营，要活到只剩你们才算赢。'},
}

ROLE_ORDER = ['wolf', 'wolfking', 'whitewolf', 'beauty', 'nightmare', 'bloodmoon', 'ghostrider',
              'gargoyle', 'mech',
              'villager',
              'seer', 'witch', 'hunter', 'guard', 'idiot', 'knight', 'psychic', 'gravekeeper',
              'dreamer', 'magician', 'witcher', 'cupid']
MULTI = ('wolf', 'villager')                     # 只有这两种可以有多张
GODS = [r for r in ROLE_ORDER if ROLES[r]['kind'] == 'god']

# 夜晚行动顺序：(环节, 板子里要有哪个角色才叫, 哪些夜晚叫)
#   first = 只在第一夜    later = 从第二夜起    always = 每晚
# 原则：会改变别人技能落点的先行动（梦魇、魔术师、摄梦人、守卫），
# 然后是狼人和依附狼刀的角色，再是要知道刀口的女巫，最后是只拿信息的角色。
NIGHT_STEPS = [
    ('cupid', 'cupid', 'first'),
    ('lovers', 'cupid', 'first'),
    ('nightmare', 'nightmare', 'always'),
    ('magician', 'magician', 'always'),
    ('dreamer', 'dreamer', 'always'),
    ('guard', 'guard', 'always'),
    ('mech', 'mech', 'always'),
    ('wolf', None, 'always'),
    ('beauty', 'beauty', 'always'),
    ('gargoyle', 'gargoyle', 'always'),
    ('witch', 'witch', 'always'),
    ('seer', 'seer', 'always'),
    ('psychic', 'psychic', 'always'),
    ('gravekeeper', 'gravekeeper', 'later'),
    ('witcher', 'witcher', 'later'),
]
STEP_NAME = {'lovers': '情侣确认', 'wolf': '狼人'}


def step_name(step):
    return STEP_NAME.get(step) or ROLES[step]['name']


def night_steps(roles, night_no):
    out = []
    for step, need, when in NIGHT_STEPS:
        if need and not roles.get(need):
            continue
        if (when == 'first' and night_no != 1) or (when == 'later' and night_no == 1):
            continue
        out.append(step)
    return out


def _p(pid, name, **roles):
    return {'id': pid, 'name': name, 'roles': roles}


PRESETS = [
    _p('p6', '6人 预女', wolf=2, villager=2, seer=1, witch=1),
    _p('p7', '7人 预女猎', wolf=2, villager=2, seer=1, witch=1, hunter=1),
    _p('p9', '9人 预女猎', wolf=3, villager=3, seer=1, witch=1, hunter=1),
    _p('p10', '10人 预女猎守', wolf=3, villager=3, seer=1, witch=1, hunter=1, guard=1),
    _p('p12a', '12人 预女猎白', wolf=4, villager=4, seer=1, witch=1, hunter=1, idiot=1),
    _p('p12b', '12人 预女猎守', wolf=4, villager=4, seer=1, witch=1, hunter=1, guard=1),
    _p('p12c', '12人 狼王守卫', wolf=3, wolfking=1, villager=4, seer=1, witch=1, hunter=1, guard=1),
    _p('p12d', '12人 白狼王守卫', wolf=3, whitewolf=1, villager=4, seer=1, witch=1, hunter=1, guard=1),
    _p('p12e', '12人 白狼王骑士', wolf=3, whitewolf=1, villager=4, seer=1, witch=1, knight=1, guard=1),
    _p('p12f', '12人 狼美人骑士', wolf=3, beauty=1, villager=4, seer=1, witch=1, knight=1, guard=1),
    _p('p12g', '12人 机械狼通灵师', wolf=3, mech=1, villager=4, psychic=1, witch=1, hunter=1, guard=1),
    _p('p12h', '12人 石像鬼守墓人', wolf=3, gargoyle=1, villager=4, seer=1, witch=1, hunter=1,
       gravekeeper=1),
    _p('p12i', '12人 梦魇守卫', wolf=3, nightmare=1, villager=4, seer=1, witch=1, hunter=1, guard=1),
    _p('p12j', '12人 恶灵骑士', wolf=3, ghostrider=1, villager=4, seer=1, witch=1, hunter=1, guard=1),
    _p('p12k', '12人 血月猎魔', wolf=3, bloodmoon=1, villager=4, seer=1, witch=1, idiot=1, witcher=1),
    _p('p12l', '12人 狼王摄梦人', wolf=3, wolfking=1, villager=4, seer=1, witch=1, hunter=1,
       dreamer=1),
    _p('p12m', '12人 狼王魔术师', wolf=3, wolfking=1, villager=4, seer=1, witch=1, hunter=1,
       magician=1),
    _p('p12n', '12人 丘比特', wolf=4, villager=4, seer=1, witch=1, hunter=1, cupid=1),
]

MIN_SEATS, MAX_SEATS = 4, 18


def full_roles(roles):
    return {r: int(roles.get(r, 0) or 0) for r in ROLE_ORDER}


def total_of(roles):
    return sum(int(roles.get(r, 0) or 0) for r in ROLE_ORDER)


DEFAULT_PRESET = 'p12a'          # 新建房间时默认的板子：12 人预女猎白


def default_config():
    roles = next(p['roles'] for p in PRESETS if p['id'] == DEFAULT_PRESET)
    return {'roles': full_roles(roles), 'witch_self_save': 'first',
            'win': 'side', 'sheriff': True}


def validate_config(cfg):
    """返回错误文字；配置可以开局时返回 None。"""
    roles = cfg['roles']
    n = total_of(roles)
    wolves = sum(roles[r] for r in ROLE_ORDER if ROLES[r]['team'] == 'wolf')
    if n < MIN_SEATS:
        return '至少需要 %d 名玩家' % MIN_SEATS
    if n > MAX_SEATS:
        return '最多支持 %d 名玩家' % MAX_SEATS
    if wolves < 1:
        return '至少需要 1 个狼人阵营的角色'
    if wolves * 2 >= n:
        return '狼人太多了，好人必须比狼人多'
    for r in ROLE_ORDER:
        if r not in MULTI and roles[r] > 1:
            return '%s 最多 1 个' % ROLES[r]['name']
    return None
