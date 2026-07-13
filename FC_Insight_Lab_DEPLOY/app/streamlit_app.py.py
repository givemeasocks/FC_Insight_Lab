import streamlit as st
import altair as alt
import pandas as pd
import requests
from pathlib import Path

st.set_page_config(
    page_title="FC Insight Lab",
    page_icon="⚽",
    layout="wide"
)

API_KEY = st.secrets["NEXON_API_KEY"]

HEADERS = {
    "x-nxopen-api-key": API_KEY
}


def get_ouid(nickname):
    url = "https://open.api.nexon.com/fconline/v1/id"

    response = requests.get(
        url,
        headers=HEADERS,
        params={"nickname": nickname}
    )

    if response.status_code != 200:
        return None

    data = response.json()
    return data.get("ouid")



def get_matchtypes():
    url = "https://open.api.nexon.com/static/fconline/meta/matchtype.json"

    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        return []

    return response.json()


def find_best_matchtype(ouid):
    matchtypes = get_matchtypes()
    match_url = "https://open.api.nexon.com/fconline/v1/user/match"

    best_matchtype_name = None
    best_match_ids = []

    for matchtype in matchtypes:
        matchtype_id = matchtype.get("matchtype")
        matchtype_name = matchtype.get("desc")

        response = requests.get(
            match_url,
            headers=HEADERS,
            params={
                "ouid": ouid,
                "matchtype": matchtype_id,
                "offset": 0,
                "limit": 20
            }
        )

        if response.status_code != 200:
            continue

        match_ids = response.json()

        if len(match_ids) > len(best_match_ids):
            best_matchtype_name = matchtype_name
            best_match_ids = match_ids

    return best_matchtype_name, best_match_ids

@st.cache_data(show_spinner=False)
def get_spid_meta():
    url = "https://open.api.nexon.com/static/fconline/meta/spid.json"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        return {}

    return {
        item.get("id"): item.get("name")
        for item in response.json()
    }


@st.cache_data(show_spinner=False)
def get_position_meta():
    url = "https://open.api.nexon.com/static/fconline/meta/spposition.json"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        return {}

    return {
        item.get("spposition"): item.get("desc")
        for item in response.json()
    }
def build_match_dataframe(ouid, nickname, matchtype_name, match_ids):
    detail_url = "https://open.api.nexon.com/fconline/v1/match-detail"

    rows = []

    for match_id in match_ids:
        response = requests.get(
            detail_url,
            headers=HEADERS,
            params={"matchid": match_id}
        )

        if response.status_code != 200:
            continue

        detail_data = response.json()

        match_info = detail_data.get("matchInfo", [])

        my_info = None
        opponent_info = None

        for player in match_info:
            if player.get("ouid") == ouid:
                my_info = player
            else:
                opponent_info = player

        if not my_info:
            continue

        my_detail = my_info.get("matchDetail", {})
        my_shoot = my_info.get("shoot", {})

        opponent_shoot = {}

        if opponent_info:
            opponent_shoot = opponent_info.get("shoot", {})

        goal_for = my_shoot.get("goalTotal") or 0
        goal_against = opponent_shoot.get("goalTotal") or 0
        shoot_total = my_shoot.get("shootTotal") or 0
        effective_shoot_total = my_shoot.get("effectiveShootTotal") or 0

        if effective_shoot_total > 0:
            conversion_rate = round(goal_for / effective_shoot_total * 100, 1)
        else:
            conversion_rate = 0

        rows.append({
            "match_id": match_id,
            "match_date": detail_data.get("matchDate"),
            "match_type": detail_data.get("matchType"),
            "match_type_name": matchtype_name,
            "nickname": nickname,
            "result": my_detail.get("matchResult"),
            "goal_for": goal_for,
            "goal_against": goal_against,
            "goal_diff": goal_for - goal_against,
            "shoot_total": shoot_total,
            "effective_shoot_total": effective_shoot_total,
            "conversion_rate": conversion_rate,
            "possession": my_detail.get("possession") or 0,
            "foul": my_detail.get("foul") or 0,
            "yellow_cards": my_detail.get("yellowCards") or 0,
            "red_cards": my_detail.get("redCards") or 0,
            "controller": my_detail.get("controller")
        })

    return pd.DataFrame(rows)


def analyze_user(df):
    total_matches = len(df)

    wins = len(df[df["result"] == "승"])
    draws = len(df[df["result"] == "무"])
    losses = len(df[df["result"] == "패"])

    win_rate = round(wins / total_matches * 100, 1)
    avg_goal_for = round(df["goal_for"].mean(), 2)
    avg_goal_against = round(df["goal_against"].mean(), 2)
    avg_goal_diff = round(df["goal_diff"].mean(), 2)
    avg_conversion_rate = round(df["conversion_rate"].mean(), 1)
    avg_possession = round(df["possession"].mean(), 1)

    goal_diff_std = df["goal_diff"].std()

    if pd.isna(goal_diff_std):
        goal_diff_std = 0

    goal_diff_std = round(goal_diff_std, 2)

    attack_score = min(round(avg_goal_for / 3 * 100), 100)
    defense_score = max(round(100 - avg_goal_against / 3 * 100), 0)
    finish_score = min(round(avg_conversion_rate), 100)
    stability_score = max(round(100 - goal_diff_std / 3 * 100), 0)

    weakness_candidates = [
        ("공격 효율", attack_score),
        ("수비 안정성", defense_score),
        ("결정력", finish_score),
        ("경기 안정성", stability_score)
    ]

    weakness_rank = sorted(weakness_candidates, key=lambda x: x[1])

    if avg_goal_for >= 2.5 and avg_goal_against >= 2:
        playstyle = "공격 몰입형"
    elif avg_goal_for < 1.5 and avg_goal_against <= 1.5:
        playstyle = "수비 안정형"
    elif avg_goal_diff < 0:
        playstyle = "성장 정체형"
    elif goal_diff_std >= 2.5:
        playstyle = "기복형"
    else:
        playstyle = "밸런스형"

    if playstyle == "공격 몰입형":
        report = (
            f"최근 {total_matches}경기 기준 평균 득점은 {avg_goal_for}점으로 높은 편이지만, "
            f"평균 실점도 {avg_goal_against}점으로 함께 높게 나타났습니다. "
            "공격 전개와 마무리 능력은 강점이지만, 수비 전환과 역습 대응에서 손실이 발생할 가능성이 있습니다."
        )
        growth = (
            "다음 성장 방향은 수비 안정화입니다. 공격력을 더 키우기보다, 현재 득점력을 유지하면서 "
            "실점 폭을 줄이는 방향이 승률 개선에 더 직접적으로 연결될 수 있습니다."
        )
        squad = [
            "CB: 속도, 몸싸움, 수비 AI가 좋은 센터백",
            "CDM: 수비 가담과 패스 연결이 안정적인 수비형 미드필더",
            "GK: 안정적인 선방 능력을 가진 골키퍼"
        ]
        items = [
            "수비수 선택형 선수팩",
            "CB/CDM 포지션 강화 재료팩",
            "수비 안정화 미션 보상",
            "포메이션 추천형 성장 이벤트"
        ]
        enhance = (
            "현재는 공격진 강화보다 수비 라인 보강 우선순위가 높습니다. "
            "고강 공격수를 추가하는 것보다 실점 원인을 줄이는 포지션에 재화를 쓰는 편이 효율적일 수 있습니다."
        )

    elif playstyle == "수비 안정형":
        report = (
            f"최근 {total_matches}경기 기준 평균 실점은 {avg_goal_against}점으로 낮은 편이지만, "
            f"평균 득점은 {avg_goal_for}점으로 다소 낮게 나타났습니다. "
            "경기를 안정적으로 운영하는 능력은 있으나, 공격 전환과 마무리 단계에서 득점 연결력이 부족할 수 있습니다."
        )
        growth = (
            "다음 성장 방향은 결정력 개선입니다. 현재의 수비 안정성을 유지하면서, "
            "박스 안에서 마무리할 수 있는 공격수나 찬스를 만들어주는 공격형 미드필더 보강이 적합합니다."
        )
        squad = [
            "ST: 결정력과 침투 움직임이 좋은 공격수",
            "CAM: 패스와 찬스 메이킹이 좋은 공격형 미드필더",
            "Winger: 측면 돌파와 크로스가 가능한 자원"
        ]
        items = [
            "공격수 선택형 선수팩",
            "ST/CAM 포지션 성장팩",
            "슈팅 훈련 미션",
            "득점 챌린지형 이벤트"
        ]
        enhance = (
            "현재는 수비 자원 강화보다 공격 핵심 자원의 업그레이드가 우선입니다. "
            "득점 생산성이 낮은 상황에서는 공격수나 공격형 미드필더 강화가 더 큰 체감으로 이어질 수 있습니다."
        )

    elif playstyle == "성장 정체형":
        report = (
            f"최근 {total_matches}경기 기준 평균 득실차가 {avg_goal_diff}점으로 낮게 나타났습니다. "
            "이는 한 포지션만의 문제가 아니라, 공격과 수비 양쪽에서 전반적인 개선이 필요할 가능성을 보여줍니다."
        )
        growth = (
            "다음 성장 방향은 스쿼드 균형 회복입니다. 먼저 득점 부족인지, 실점 과다인지 확인한 뒤 "
            "가장 큰 손실 지표부터 개선하는 것이 좋습니다."
        )
        squad = [
            "팀 전체 밸런스 점검",
            "득점 부족 시 ST/CAM 보강",
            "실점 과다 시 CB/CDM/GK 보강"
        ]
        items = [
            "종합 성장 패키지",
            "BP 보강팩",
            "선택형 선수팩",
            "강화 재료 지원 이벤트"
        ]
        enhance = (
            "현재는 특정 선수 강화보다 스쿼드 구조 점검이 먼저입니다. "
            "강화 전, 해당 선수가 실제 약점 포지션에 해당하는지 확인하는 것이 필요합니다."
        )

    elif playstyle == "기복형":
        report = (
            f"최근 {total_matches}경기 기준 경기별 득실차 변동이 {goal_diff_std}로 크게 나타났습니다. "
            "좋은 흐름을 만드는 경기와 흔들리는 경기의 차이가 있는 유형입니다."
        )
        growth = (
            "다음 성장 방향은 경기력 변동성 축소입니다. 공격과 수비 중 한쪽에만 투자하기보다, "
            "중원 장악력과 수비 전환을 안정화하는 방향이 좋습니다."
        )
        squad = [
            "CDM: 수비 전환과 볼 배급을 모두 담당할 수 있는 자원",
            "CM: 경기 템포를 안정적으로 잡아주는 미드필더",
            "CB: 실점 폭을 줄여주는 안정형 수비수"
        ]
        items = [
            "미드필더 선택형 선수팩",
            "밸런스형 성장팩",
            "연승 유지 미션",
            "전술 적응 챌린지"
        ]
        enhance = (
            "현재는 한 선수에게 고강화를 몰아주기보다, 경기 흐름을 안정화할 수 있는 중원 자원 보강이 우선입니다."
        )

    else:
        report = (
            f"최근 {total_matches}경기 기준 득점, 실점, 승률 흐름이 비교적 균형적인 편입니다. "
            "특정 지표가 크게 무너지지는 않았기 때문에 현재 스쿼드의 기본 완성도는 어느 정도 확보된 상태로 볼 수 있습니다."
        )
        growth = (
            "다음 성장 방향은 세부 효율 개선입니다. 큰 구조를 바꾸기보다, 현재 스쿼드에서 가장 자주 사용하는 포지션의 "
            "체감 성능을 높이거나 랭커들이 선호하는 포지션 구성을 참고해 미세 조정하는 방식이 적합합니다."
        )
        squad = [
            "주전 핵심 포지션 업그레이드",
            "자주 사용하는 공격 루트에 맞는 보조 포지션 보강",
            "랭커 메타와 비교한 약점 포지션 보완"
        ]
        items = [
            "선택형 선수팩",
            "상위 티어 도전 패스",
            "랭커 스쿼드 비교 콘텐츠",
            "핵심 포지션 강화 재료팩"
        ]
        enhance = (
            "현재는 무리한 전체 교체보다 핵심 주전 카드의 단계적 강화가 적합합니다. "
            "다만 강화 전에는 해당 선수가 장기적으로 사용할 카드인지 먼저 확인하는 것이 좋습니다."
        )

    return {
        "total_matches": total_matches,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "win_rate": win_rate,
        "avg_goal_for": avg_goal_for,
        "avg_goal_against": avg_goal_against,
        "avg_goal_diff": avg_goal_diff,
        "avg_conversion_rate": avg_conversion_rate,
        "avg_possession": avg_possession,
        "goal_diff_std": goal_diff_std,
        "attack_score": attack_score,
        "defense_score": defense_score,
        "finish_score": finish_score,
        "stability_score": stability_score,
        "weakness_rank": weakness_rank,
        "playstyle": playstyle,
        "report": report,
        "growth": growth,
        "squad": squad,
        "items": items,
        "enhance": enhance
    }

def make_growth_recommendation(analysis):
    playstyle = analysis["playstyle"]
    primary_weakness = analysis["weakness_rank"][0][0]

    if playstyle == "공격 몰입형" or primary_weakness == "수비 안정성":
        title = "수비 안정화 추천"
        growth_point = "실점 관리와 수비 안정성 개선"
        recommended_items = [
            "수비수 선택형 선수팩",
            "CB/CDM 포지션 강화 재료팩",
            "수비 안정화 미션 패스",
            "골키퍼/수비 라인 보강 패키지"
        ]
        reason = (
            "최근 경기에서 공격 생산성은 확보되어 있지만 수비 안정성이 낮게 나타났습니다. "
            "따라서 공격수 추가 강화보다 수비 라인 보강이 승률 개선에 더 직접적으로 연결될 수 있습니다."
        )

    elif playstyle == "수비 안정형" or primary_weakness in ["공격 효율", "결정력"]:
        title = "득점력 강화 추천"
        growth_point = "득점 생산성과 결정력 개선"
        recommended_items = [
            "공격수 선택형 선수팩",
            "ST/CAM 포지션 성장 패키지",
            "슈팅/득점 미션 이벤트",
            "공격 핵심 선수 강화 재료팩"
        ]
        reason = (
            "수비 운영은 비교적 안정적이지만 득점 생산성이 낮게 나타났습니다. "
            "공격수 또는 공격형 미드필더 보강이 현재 성장 방향과 잘 맞습니다."
        )

    elif playstyle == "성장 정체형":
        title = "스쿼드 균형 성장 추천"
        growth_point = "전체 스쿼드 균형 회복"
        recommended_items = [
            "BP 보강 패키지",
            "종합 성장 지원팩",
            "선택형 선수팩",
            "복귀/성장 미션 패스"
        ]
        reason = (
            "득점과 실점 지표가 함께 불안정하게 나타나 특정 포지션 하나보다 전체 스쿼드 보강이 필요합니다. "
            "고가 단일 선수보다 여러 포지션을 단계적으로 보완하는 방향이 적합합니다."
        )

    elif playstyle == "기복형" or primary_weakness == "경기 안정성":
        title = "경기 운영 안정화 추천"
        growth_point = "경기 흐름 안정화와 중원 보강"
        recommended_items = [
            "미드필더 선택형 선수팩",
            "CM/CDM 포지션 강화 재료팩",
            "연승 유지 미션 이벤트",
            "밸런스형 성장 패키지"
        ]
        reason = (
            "경기별 득실차 변동이 커서 안정적인 경기 운영이 필요한 유형입니다. "
            "공격수 고강화보다 중원 장악력과 수비 전환을 보완하는 방향이 더 적합할 수 있습니다."
        )

    else:
        title = "상위 단계 성장 추천"
        growth_point = "핵심 주전 포지션의 단계적 업그레이드"
        recommended_items = [
            "핵심 포지션 강화 재료팩",
            "상위 티어 도전 패스",
            "선택형 선수팩",
            "랭커 스쿼드 비교 기반 성장 이벤트"
        ]
        reason = (
            "전체 지표가 비교적 균형적인 유저는 큰 구조 변화보다 핵심 주전 카드의 단계적 강화가 적합합니다. "
            "상위 단계 진입을 목표로 하는 성장형 아이템과 잘 맞습니다."
        )

    return {
        "title": title,
        "growth_point": growth_point,
        "recommended_items": recommended_items,
        "reason": reason
    }
def make_enhancement_decision(analysis):
    playstyle = analysis["playstyle"]
    attack_score = analysis["attack_score"]
    defense_score = analysis["defense_score"]
    finish_score = analysis["finish_score"]
    stability_score = analysis["stability_score"]
    primary_weakness = analysis["weakness_rank"][0][0]

    if defense_score <= 50 and attack_score >= 60:
        decision = "강화 보류 · 수비진 보강 우선"
        target_position = "CB / CDM / GK"
        reason = (
            "공격 효율은 비교적 확보되어 있지만 수비 안정성 점수가 낮게 나타났습니다. "
            "현재는 공격수 고강화보다 실점을 줄일 수 있는 수비 라인 보강이 우선입니다."
        )
        action = [
            "공격진 강화 재화 사용은 일단 보류",
            "CB/CDM/GK 포지션 보강 우선 검토",
            "실점 감소 후 핵심 선수 강화 진행"
        ]

    elif attack_score <= 50 or finish_score <= 35:
        decision = "공격 핵심 자원 강화 검토"
        target_position = "ST / CAM / Winger"
        reason = (
            "득점 생산성 또는 결정력 점수가 낮게 나타났습니다. "
            "찬스를 득점으로 연결할 수 있는 공격 핵심 자원의 강화 또는 교체를 검토할 필요가 있습니다."
        )
        action = [
            "주전 ST/CAM의 체감 성능 점검",
            "결정력 높은 공격 자원 보강",
            "공격 포지션 강화 재료 사용 검토"
        ]

    elif stability_score <= 50 or primary_weakness == "경기 안정성":
        decision = "중원 안정화 후 강화 추천"
        target_position = "CM / CDM"
        reason = (
            "경기 안정성 점수가 낮아 경기별 흐름 차이가 큰 상태입니다. "
            "단일 공격수 강화보다 중원 장악력과 수비 전환을 안정화한 뒤 강화하는 편이 효율적입니다."
        )
        action = [
            "CM/CDM 포지션 보강 우선",
            "중원 안정화 후 공격·수비 핵심 카드 강화",
            "기복이 큰 포지션부터 순차 점검"
        ]

    elif playstyle == "성장 정체형":
        decision = "고강화보다 전체 스쿼드 보강 우선"
        target_position = "전체 스쿼드"
        reason = (
            "전체 지표가 낮은 상태에서는 한 명의 선수를 고강화하는 것보다 "
            "여러 포지션의 기본 전력을 끌어올리는 편이 성장 체감이 클 수 있습니다."
        )
        action = [
            "고가 단일 강화는 보류",
            "BP 또는 종합 성장 자원 확보",
            "약점 포지션 1~2개부터 순차 보강"
        ]

    else:
        decision = "핵심 주전 카드 단계적 강화 추천"
        target_position = "주전 핵심 포지션"
        reason = (
            "전체 지표가 비교적 균형적인 상태입니다. "
            "큰 폭의 스쿼드 교체보다 자주 사용하는 핵심 주전 카드의 단계적 강화가 적합합니다."
        )
        action = [
            "가장 자주 사용하는 주전 카드 우선 강화",
            "현재 전술과 맞는 선수인지 확인",
            "무리한 고강화보다 단계적 강화 진행"
        ]

    return {
        "decision": decision,
        "target_position": target_position,
        "reason": reason,
        "action": action
    }
def make_position_recommendation(analysis):
    attack_score = analysis["attack_score"]
    defense_score = analysis["defense_score"]
    finish_score = analysis["finish_score"]
    stability_score = analysis["stability_score"]
    avg_goal_for = analysis["avg_goal_for"]
    avg_goal_against = analysis["avg_goal_against"]
    playstyle = analysis["playstyle"]

    recommendations = []

    if defense_score <= 55 or avg_goal_against >= 2:
        recommendations.append({
            "priority": "1순위",
            "position": "CB / CDM",
            "reason": "평균 실점 또는 수비 안정성 지표가 낮아 수비 라인과 수비형 미드필더 보강이 필요합니다.",
            "expected_effect": "실점 감소, 역습 대응 개선, 경기 안정성 향상"
        })

    if attack_score <= 55 or avg_goal_for < 1.5:
        recommendations.append({
            "priority": "1순위",
            "position": "ST / CAM",
            "reason": "평균 득점 또는 공격 효율 지표가 낮아 득점 생산성을 높일 공격 자원 보강이 필요합니다.",
            "expected_effect": "득점력 개선, 찬스 마무리 강화, 공격 루트 다양화"
        })

    if finish_score <= 40:
        recommendations.append({
            "priority": "2순위",
            "position": "ST / Winger",
            "reason": "유효슈팅 대비 득점률이 낮아 결정력과 마무리 능력을 보완할 필요가 있습니다.",
            "expected_effect": "결정력 개선, 박스 안 마무리 강화"
        })

    if stability_score <= 55 or playstyle == "기복형":
        recommendations.append({
            "priority": "2순위",
            "position": "CM / CDM",
            "reason": "경기별 득실차 변동이 커서 중원에서 경기 흐름을 안정화할 필요가 있습니다.",
            "expected_effect": "경기 운영 안정화, 수비 전환 개선, 점유 흐름 안정"
        })

    if not recommendations:
        recommendations.append({
            "priority": "1순위",
            "position": "주전 핵심 포지션",
            "reason": "전체 지표가 비교적 균형적이므로 가장 자주 사용하는 핵심 포지션의 단계적 업그레이드가 적합합니다.",
            "expected_effect": "상위 단계 진입, 주전 체감 성능 향상"
        })

        recommendations.append({
            "priority": "2순위",
            "position": "전술 보조 포지션",
            "reason": "현재 주 전술에서 자주 활용하는 공격 루트나 수비 약점을 기준으로 보조 포지션을 보완하면 좋습니다.",
            "expected_effect": "전술 완성도 향상, 경기별 대응력 개선"
        })

    return recommendations[:3]

def build_player_summary(ouid, match_ids):
    detail_url = "https://open.api.nexon.com/fconline/v1/match-detail"

    spid_meta = get_spid_meta()
    position_meta = get_position_meta()

    rows = []

    for match_id in match_ids:
        response = requests.get(
            detail_url,
            headers=HEADERS,
            params={"matchid": match_id}
        )

        if response.status_code != 200:
            continue

        detail_data = response.json()
        match_info = detail_data.get("matchInfo", [])

        my_info = None

        for user_info in match_info:
            if user_info.get("ouid") == ouid:
                my_info = user_info
                break

        if not my_info:
            continue

        players = my_info.get("player", [])

        for player in players:
            status = player.get("status", {})

            sp_id = player.get("spId")
            position_id = player.get("spPosition")

            rows.append({
                "match_id": match_id,
                "sp_id": sp_id,
                "player_name": spid_meta.get(sp_id, f"선수ID {sp_id}"),
                "position_name": position_meta.get(position_id, f"포지션 {position_id}"),
                "sp_grade": player.get("spGrade", 0),
                "goal": status.get("goal", 0),
                "assist": status.get("assist", 0),
                "shoot": status.get("shoot", 0),
                "effective_shoot": status.get("effectiveShoot", 0),
                "pass_success": status.get("passSuccess", 0),
                "pass_try": status.get("passTry", 0),
                "rating": status.get("spRating", 0)
            })

    player_df = pd.DataFrame(rows)

    if player_df.empty:
        return pd.DataFrame()

    summary = player_df.groupby(
        ["sp_id", "player_name", "position_name"],
        as_index=False
    ).agg(
        appearances=("match_id", "nunique"),
        max_grade=("sp_grade", "max"),
        goals=("goal", "sum"),
        assists=("assist", "sum"),
        shoots=("shoot", "sum"),
        effective_shoots=("effective_shoot", "sum"),
        pass_success=("pass_success", "sum"),
        pass_try=("pass_try", "sum"),
        avg_rating=("rating", "mean")
    )

    summary["avg_rating"] = summary["avg_rating"].round(2)

    summary["attack_contribution"] = (
        summary["goals"] * 3
        + summary["assists"] * 2
        + summary["effective_shoots"] * 1.5
        + summary["shoots"] * 0.5
    )

    summary["attack_contribution"] = summary["attack_contribution"].round(1)

    return summary
def render_dashboard(df, player_summary=None):
    df["match_date"] = pd.to_datetime(df["match_date"])
    df = df.sort_values("match_date")

    analysis = analyze_user(df)

    nickname = df["nickname"].iloc[0]
    match_type_name = df["match_type_name"].iloc[0]

    st.divider()

    st.markdown(f"### 분석 구단주님: `{nickname}`")
    st.write(f"분석 기준 매치 타입: **{match_type_name}**")
    st.write(f"분석 경기 수: **{analysis['total_matches']}경기**")

    st.markdown("## 📌 핵심 요약")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("승률", f"{analysis['win_rate']}%")
    col2.metric("평균 득점", analysis["avg_goal_for"])
    col3.metric("평균 실점", analysis["avg_goal_against"])
    col4.metric("평균 득실차", analysis["avg_goal_diff"])

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("승/무/패", f"{analysis['wins']}승 {analysis['draws']}무 {analysis['losses']}패")
    col6.metric("평균 유효슈팅 득점률", f"{analysis['avg_conversion_rate']}%")
    col7.metric("평균 점유율", f"{analysis['avg_possession']}%")
    col8.metric("경기 기복 지표", analysis["goal_diff_std"])

    st.divider()

    st.markdown("## 🧭 플레이 종합 진단")

    score_col1, score_col2, score_col3, score_col4 = st.columns(4)
    score_col1.metric("공격 효율", f"{analysis['attack_score']}점")
    score_col2.metric("수비 안정성", f"{analysis['defense_score']}점")
    score_col3.metric("결정력", f"{analysis['finish_score']}점")
    score_col4.metric("경기 안정성", f"{analysis['stability_score']}점")

    st.markdown("### 🔎 약점 우선순위")

    for idx, (name, score) in enumerate(analysis["weakness_rank"][:3], start=1):
        st.write(f"{idx}순위: **{name} 개선 필요** · 현재 점수 {score}점")

    st.caption("진단 점수는 최근 경기 데이터를 기반으로 만든 포트폴리오용 간이 지표입니다.")
    st.divider()

    st.markdown("## 🏆 랭커 대비 성장 목표")

    st.caption(
        "현재 2026.06월 기준 랭커 기준값과 비교한 결과입니다. 추후 랭커 API 데이터로 업데이트 및 자동화 예정입니다."
    )

    ranker_avg_goal_for = 2.4
    ranker_avg_goal_against = 1.2
    ranker_avg_conversion_rate = 45.0
    ranker_avg_possession = 52.0

    st.write("**평균 득점**")
    st.write(f"- 내 지표: {analysis['avg_goal_for']} / 랭커 기준: {ranker_avg_goal_for} / 차이: {round(analysis['avg_goal_for'] - ranker_avg_goal_for, 2)}")

    st.write("**평균 실점**")
    st.write(f"- 내 지표: {analysis['avg_goal_against']} / 랭커 기준: {ranker_avg_goal_against} / 차이: {round(analysis['avg_goal_against'] - ranker_avg_goal_against, 2)}")

    st.write("**유효슈팅 득점률**")
    st.write(f"- 내 지표: {analysis['avg_conversion_rate']}% / 랭커 기준: {ranker_avg_conversion_rate}% / 차이: {round(analysis['avg_conversion_rate'] - ranker_avg_conversion_rate, 1)}%")

    st.write("**평균 점유율**")
    st.write(f"- 내 지표: {analysis['avg_possession']}% / 랭커 기준: {ranker_avg_possession}% / 차이: {round(analysis['avg_possession'] - ranker_avg_possession, 1)}%")

    st.markdown("### 추천 훈련 목표")

    if analysis["avg_goal_for"] < ranker_avg_goal_for:
        st.write("- 평균 득점 +0.5 개선")

    if analysis["avg_goal_against"] > ranker_avg_goal_against:
        st.write("- 평균 실점 -0.5 개선")

    if analysis["avg_conversion_rate"] < ranker_avg_conversion_rate:
        st.write("- 유효슈팅 득점률 개선")

    if analysis["avg_possession"] < ranker_avg_possession:
        st.write("- 점유율과 중원 운영 안정화")

    if (
        analysis["avg_goal_for"] >= ranker_avg_goal_for
        and analysis["avg_goal_against"] <= ranker_avg_goal_against
        and analysis["avg_conversion_rate"] >= ranker_avg_conversion_rate
        and analysis["avg_possession"] >= ranker_avg_possession
    ):
        st.write("- 현재 강점을 유지하면서 핵심 포지션 단계적 강화")
    st.divider()

    st.markdown("## 📈 경기 흐름")

    flow_df = df.reset_index(drop=True).copy()
    flow_df["경기 번호"] = flow_df.index + 1

    flow_chart_df = flow_df[
        ["경기 번호", "goal_for", "goal_against", "goal_diff"]
    ].rename(columns={
        "goal_for": "득점",
        "goal_against": "실점",
        "goal_diff": "득실차"
    })

    flow_chart_df = flow_chart_df.melt(
        id_vars="경기 번호",
        var_name="지표",
        value_name="값"
    )

    flow_chart = alt.Chart(flow_chart_df).mark_line(point=True).encode(
        x=alt.X(
            "경기 번호:O",
            axis=alt.Axis(title="최근 경기 순서", labelAngle=0)
        ),
        y=alt.Y(
    "값:Q",
    axis=alt.Axis(
        title="골 수",
        titleAngle=0,
        titleAlign="left",
        titlePadding=25
    )
),
        color=alt.Color(
            "지표:N",
            legend=alt.Legend(title=None)
        ),
        tooltip=["경기 번호", "지표", "값"]
    ).properties(
        height=300
    )

    st.altair_chart(flow_chart, use_container_width=True)

    st.markdown("## 승/무/패 분포")

    result_counts = df["result"].value_counts().reindex(["승", "무", "패"], fill_value=0)

    result_chart_df = pd.DataFrame({
        "결과": result_counts.index,
        "경기 수": result_counts.values
    })

    result_chart = alt.Chart(result_chart_df).mark_bar(
        cornerRadiusTopLeft=6,
        cornerRadiusTopRight=6
    ).encode(
        x=alt.X(
            "결과:N",
            sort=["승", "무", "패"],
            axis=alt.Axis(title=None, labelAngle=0)
        ),
        y=alt.Y(
    "경기 수:Q",
    axis=alt.Axis(
        title="경기 수",
        titleAngle=0,
        titleAlign="left",
        titlePadding=25,
        tickMinStep=1
    )
        ),
        color=alt.Color(
            "결과:N",
            scale=alt.Scale(
                domain=["승", "무", "패"],
                range=["#2E7D32", "#9E9E9E", "#C62828"]
            ),
            legend=None
        ),
        tooltip=["결과", "경기 수"]
        ).properties(
        height=260
    )

    st.altair_chart(result_chart, use_container_width=True)

    st.divider()

    st.markdown("## 최근 경기 상세 데이터")

    display_columns = [
        "match_date",
        "result",
        "goal_for",
        "goal_against",
        "goal_diff",
        "shoot_total",
        "effective_shoot_total",
        "conversion_rate",
        "possession",
        "foul",
        "yellow_cards",
        "red_cards",
        "controller"
    ]

    st.dataframe(df[display_columns], use_container_width=True)
    csv_download = df.to_csv(index=False, encoding="utf-8-sig")

    st.download_button(
        label="분석 데이터 CSV 다운로드",
        data=csv_download,
        file_name="fc_insight_match_summary.csv",
        mime="text/csv"
    )
    st.divider()

    st.markdown("## 플레이 성향 리포트")
    st.info(f"플레이 유형: {analysis['playstyle']}")
    st.write(analysis["report"])

    st.markdown("## 맞춤 성장 제안")
    st.write(analysis["growth"])

    st.markdown("## 스쿼드 보강 방향")
    for text in analysis["squad"]:
        st.write(f"- {text}")
        position_recommendations = make_position_recommendation(analysis)

    st.markdown("## 🧩 포지션 보강 우선순위")

    for item in position_recommendations:
        st.write(f"**{item['priority']}: {item['position']}**")
        st.write(f"- 추천 이유: {item['reason']}")
        st.write(f"- 기대 효과: {item['expected_effect']}")
    if player_summary is not None and not player_summary.empty:
        st.markdown("## 👟 선수 활용 분석")

        st.markdown("### 자주 활용한 선수 TOP 3")

        top_used_players = player_summary.sort_values(
            ["appearances", "attack_contribution"],
            ascending=False
        ).head(3)

        st.dataframe(
            top_used_players[
                [
                    "player_name",
                    "position_name",
                    "appearances",
                    "max_grade",
                    "goals",
                    "assists",
                    "effective_shoots",
                    "avg_rating",
                    "attack_contribution"
                ]
            ],
            use_container_width=True
        )

        st.markdown("### 공격 기여 개선 검토 선수 TOP 3")

        improvement_candidates = player_summary[
            player_summary["position_name"] != "GK"
        ].copy()

        if not improvement_candidates.empty:
            improvement_candidates = improvement_candidates.sort_values(
                ["appearances", "attack_contribution", "avg_rating"],
                ascending=[False, True, True]
            ).head(3)

            st.dataframe(
                improvement_candidates[
                    [
                        "player_name",
                        "position_name",
                        "appearances",
                        "max_grade",
                        "goals",
                        "assists",
                        "effective_shoots",
                        "avg_rating",
                        "attack_contribution"
                    ]
                ],
                use_container_width=True
            )

            st.caption(
                "출전 빈도는 높지만 공격 기여도가 낮은 선수를 우선 검토 대상으로 표시합니다. "
                "선수 교체나 포지션 보강 판단의 참고 지표로 활용할 수 있습니다."
            )

        st.divider()
    growth_recommendation = make_growth_recommendation(analysis)

    st.markdown("## 🎯 맞춤 성장 가이드")
    st.info(growth_recommendation["title"])

    st.write(f"**현재 성장 포인트:** {growth_recommendation['growth_point']}")
    st.write(growth_recommendation["reason"])

    st.markdown("### 추천 성장 아이템/이벤트")
    for item in growth_recommendation["recommended_items"]:
        st.write(f"- {item}")

    st.caption(
        "현재 플레이 성향과 약점 지표를 기준으로 참고할 수 있는 성장 방향입니다."
    )

    st.divider()

    enhancement = make_enhancement_decision(analysis)

    st.markdown("## ⚖️ 강화 판단 체크")
    st.warning(enhancement["decision"])

    st.write(f"**우선 검토 포지션:** {enhancement['target_position']}")
    st.write(enhancement["reason"])

    st.markdown("### 추천 액션")
    for action in enhancement["action"]:
        st.write(f"- {action}")
        st.divider()

    st.markdown("## 분석 기준 및 한계")

    st.write(
        "본 대시보드는 최근 경기 데이터를 기반으로 유저의 플레이 성향과 성장 방향을 추정합니다. "
        "따라서 실제 게임 내 모든 변수나 유저의 보유 선수, 예산, 선호 포메이션을 완전히 반영하지는 않습니다."
    )

    st.write(
        "다만 득점, 실점, 결정력, 경기 안정성, 선수 활용 데이터를 기준으로 "
        "유저가 어떤 성장 니즈를 가질 가능성이 높은지 판단하고, 이를 포지션 보강과 강화 방향으로 연결하는 데 목적이 있습니다."
    )

    st.caption(
        "전적 조회를 넘어, 유저 세그먼트별 성장 니즈와 상품/이벤트 반응 가능성을 연결하는 분석 구조를 보여주는 것이 핵심입니다."
    )

st.title("FC Insight Lab")
st.subheader("FC온라인 매치 데이터 기반 유저 플레이 성향 분석 대시보드")
st.sidebar.title("FC Insight Lab")

st.sidebar.markdown("### 프로젝트 개요")
st.sidebar.write(
    "최근 FC온라인 매치 데이터를 바탕으로 유저의 플레이 성향과 약점 지표를 분석하고, "
    "더 나은 경기 운영을 위한 성장 방향과 보강 우선순위를 제안합니다."
)

st.sidebar.markdown("### 분석 기준")
st.sidebar.write("- 최근 경기 승률, 득점, 실점 흐름")
st.sidebar.write("- 유효슈팅 득점률과 결정력")
st.sidebar.write("- 공격/수비/경기 안정성 지표")
st.sidebar.write("- 랭커 기준 지표값 차이")
st.sidebar.write("- 선수 활용도와 포지션별 기여도")

st.sidebar.markdown("### 제공 기능")
st.sidebar.write("- 플레이 유형 분석")
st.sidebar.write("- 약점 우선순위 진단")
st.sidebar.write("- 랭커 대비 성장 목표 제안")
st.sidebar.write("- 포지션 보강 우선순위 추천")
st.sidebar.write("- 선수 활용 분석")
st.sidebar.write("- 강화 판단 및 성장 방향 제안")

st.sidebar.markdown("### 안내")
st.sidebar.write(
    "본 대시보드는 최근 경기 데이터를 기반으로 성장 방향을 제안하는 참고용 분석 도구입니다."
)

st.sidebar.divider()
st.sidebar.caption("Created by 장아영")

st.write(
    "구단주명을 입력하면 최근 경기 데이터를 조회해 승률, 득실점 흐름, 플레이 성향, "
    "스쿼드 보강 방향을 자동으로 분석합니다."
)

st.divider()

nickname_input = st.text_input(
    "구단주명을 입력하세요",
    placeholder="예: 태연"
)

analyze_button = st.button("분석 시작")

if analyze_button:
    nickname = nickname_input.strip()

    if not nickname:
        st.warning("구단주명을 입력해주세요.")

    else:
        df = None
        player_summary = None

        try:
            with st.spinner("매치 데이터를 분석하고 있습니다."):
                ouid = get_ouid(nickname)

                if not ouid:
                    st.warning("해당 구단주명을 찾을 수 없습니다. 구단주명을 다시 확인해주세요.")

                else:
                    matchtype_name, match_ids = find_best_matchtype(ouid)

                    if not match_ids:
                        st.warning("최근 분석 가능한 공식경기 데이터를 찾지 못했습니다.")

                    else:
                        match_ids = match_ids[:5]

                        df = build_match_dataframe(
                            ouid,
                            nickname,
                            matchtype_name,
                            match_ids
                        )

                        if df is None or df.empty:
                            st.warning("분석 가능한 경기 데이터가 부족합니다. 다른 구단주명으로 다시 시도해주세요.")
                            df = None

                        player_summary = None

            if df is not None:
                st.success("분석이 완료되었습니다.")
                render_dashboard(df, player_summary)

        except Exception:
            st.error("일시적으로 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
            st.caption("외부 API 호출 제한, 일시적인 응답 오류, 또는 해당 구단주의 최근 경기 데이터 부족으로 인해 분석이 중단되었을 수 있습니다.")
else:
    st.info("구단주명을 입력하고 **분석 시작** 버튼을 눌러 주세요.")
    


    
    



    


    
