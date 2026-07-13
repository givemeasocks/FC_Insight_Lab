import streamlit as st
import pandas as pd
import requests
import altair as alt

st.set_page_config(
    page_title="FC Insight Lab",
    page_icon="⚽",
    layout="wide"
)

try:
    API_KEY = st.secrets["NEXON_API_KEY"]
except Exception:
    st.error("NEXON API Key가 설정되지 않았습니다.")
    st.stop()

HEADERS = {
    "x-nxopen-api-key": API_KEY
}


def get_json(url, params=None):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=10
        )

        if response.status_code != 200:
            return None, f"API 오류 {response.status_code}"

        return response.json(), None

    except Exception as e:
        return None, str(e)


def get_ouid(nickname):
    url = "https://open.api.nexon.com/fconline/v1/id"
    data, error = get_json(url, params={"nickname": nickname})

    if error or not data:
        return None

    return data.get("ouid")


@st.cache_data(show_spinner=False)
def get_matchtypes():
    url = "https://open.api.nexon.com/static/fconline/meta/matchtype.json"
    data, error = get_json(url)

    if error or not data:
        return []

    return data


def find_best_matchtype(ouid):
    matchtypes = get_matchtypes()
    match_url = "https://open.api.nexon.com/fconline/v1/user/match"

    official_types = [
        item for item in matchtypes
        if "공식" in str(item.get("desc", ""))
    ]

    other_types = [
        item for item in matchtypes
        if item not in official_types
    ]

    ordered_types = official_types + other_types[:5]

    best_matchtype_name = None
    best_match_ids = []

    for matchtype in ordered_types:
        matchtype_id = matchtype.get("matchtype")
        matchtype_name = matchtype.get("desc")

        data, error = get_json(
            match_url,
            params={
                "ouid": ouid,
                "matchtype": matchtype_id,
                "offset": 0,
                "limit": 5
            }
        )

        if error or not data:
            continue

        if len(data) > len(best_match_ids):
            best_matchtype_name = matchtype_name
            best_match_ids = data

    return best_matchtype_name, best_match_ids[:3]


def build_match_dataframe(ouid, nickname, matchtype_name, match_ids):
    detail_url = "https://open.api.nexon.com/fconline/v1/match-detail"
    rows = []

    for match_id in match_ids:
        detail_data, error = get_json(
            detail_url,
            params={"matchid": match_id}
        )

        if error or not detail_data:
            continue

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
        effective_shoot_total = my_shoot.get("effectiveShootTotal") or 0

        if effective_shoot_total > 0:
            conversion_rate = round(goal_for / effective_shoot_total * 100, 1)
        else:
            conversion_rate = 0

        rows.append({
            "경기일": detail_data.get("matchDate"),
            "매치유형": matchtype_name,
            "결과": my_detail.get("matchResult"),
            "득점": goal_for,
            "실점": goal_against,
            "득실차": goal_for - goal_against,
            "유효슈팅": effective_shoot_total,
            "결정력": conversion_rate,
            "점유율": my_detail.get("possession") or 0
        })

    return pd.DataFrame(rows)


def analyze_user(df):
    total_matches = len(df)
    wins = len(df[df["결과"] == "승"])
    draws = len(df[df["결과"] == "무"])
    losses = len(df[df["결과"] == "패"])

    win_rate = round(wins / total_matches * 100, 1)
    avg_goal_for = round(df["득점"].mean(), 2)
    avg_goal_against = round(df["실점"].mean(), 2)
    avg_conversion = round(df["결정력"].mean(), 1)
    avg_possession = round(df["점유율"].mean(), 1)

    if avg_goal_for >= 2 and avg_goal_against >= 2:
        playstyle = "공격 몰입형"
        recommendation = "득점력은 확보되어 있으나 실점 관리가 필요합니다. 수비 라인과 CDM 보강이 우선입니다."
    elif avg_goal_for < 1.5 and avg_goal_against <= 1.5:
        playstyle = "수비 안정형"
        recommendation = "수비는 안정적이지만 득점 생산성이 낮습니다. ST 또는 CAM 보강이 적합합니다."
    elif avg_goal_for < avg_goal_against:
        playstyle = "성장 정체형"
        recommendation = "득실 균형이 무너진 상태입니다. 특정 선수 강화보다 스쿼드 균형 점검이 먼저입니다."
    else:
        playstyle = "밸런스형"
        recommendation = "전체 지표가 비교적 균형적입니다. 핵심 주전 포지션을 단계적으로 업그레이드하는 방향이 적합합니다."

    return {
        "total_matches": total_matches,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "win_rate": win_rate,
        "avg_goal_for": avg_goal_for,
        "avg_goal_against": avg_goal_against,
        "avg_conversion": avg_conversion,
        "avg_possession": avg_possession,
        "playstyle": playstyle,
        "recommendation": recommendation
    }


def render_dashboard(df):
    analysis = analyze_user(df)

    st.success("분석이 완료되었습니다.")

    st.subheader("핵심 요약")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("최근 경기 수", f"{analysis['total_matches']}경기")
    col2.metric("승률", f"{analysis['win_rate']}%")
    col3.metric("평균 득점", analysis["avg_goal_for"])
    col4.metric("평균 실점", analysis["avg_goal_against"])

    st.subheader("플레이 성향 진단")
    st.info(f"진단 유형: {analysis['playstyle']}")
    st.write(analysis["recommendation"])

    st.subheader("경기별 득실 흐름")

    chart_df = df.reset_index().rename(columns={"index": "경기번호"})
    chart_df["경기번호"] = chart_df["경기번호"] + 1

    line_df = chart_df.melt(
        id_vars=["경기번호"],
        value_vars=["득점", "실점", "득실차"],
        var_name="지표",
        value_name="값"
    )

    line_chart = alt.Chart(line_df).mark_line(point=True).encode(
        x=alt.X("경기번호:O", title="최근 경기"),
        y=alt.Y("값:Q", title="골 수"),
        color=alt.Color("지표:N", title="지표"),
        tooltip=["경기번호", "지표", "값"]
    ).properties(height=320)

    st.altair_chart(line_chart, use_container_width=True)

    st.subheader("승/무/패 분포")

    result_df = df["결과"].value_counts().reset_index()
    result_df.columns = ["결과", "경기 수"]

    bar_chart = alt.Chart(result_df).mark_bar().encode(
        x=alt.X("결과:N", title="결과"),
        y=alt.Y("경기 수:Q", title="경기 수"),
        tooltip=["결과", "경기 수"]
    ).properties(height=300)

    st.altair_chart(bar_chart, use_container_width=True)

    st.subheader("최근 경기 상세 데이터")
    st.dataframe(df, use_container_width=True)

    st.subheader("성장 방향 제안")
    st.write("- 득점이 낮으면 ST/CAM 중심의 공격 자원 보강을 우선 검토합니다.")
    st.write("- 실점이 높으면 CB/CDM/GK 중심의 수비 안정화가 우선입니다.")
    st.write("- 득실차 변동이 크면 중원 장악력과 수비 전환 안정화가 필요합니다.")

    st.caption("본 대시보드는 NEXON Open API 기반 실시간 매치 데이터를 활용한 포트폴리오용 분석 도구입니다.")


st.title("FC Insight Lab")
st.subheader("FC온라인 매치 데이터 기반 유저 플레이 성향 분석 대시보드")

st.write(
    "구단주명을 입력하면 최근 경기 데이터를 바탕으로 승률, 득점, 실점, 결정력, 점유율을 분석하고 "
    "플레이 성향과 성장 방향을 제안합니다."
)

st.sidebar.title("FC Insight Lab")
st.sidebar.markdown("### 프로젝트 개요")
st.sidebar.write(
    "FC온라인 유저의 최근 매치 데이터를 분석해 플레이 성향과 성장 방향을 제안하는 데이터 기반 대시보드입니다."
)

st.sidebar.markdown("### 분석 항목")
st.sidebar.write("- 최근 경기 승률")
st.sidebar.write("- 평균 득점 / 실점")
st.sidebar.write("- 결정력")
st.sidebar.write("- 점유율")
st.sidebar.write("- 플레이 성향")
st.sidebar.write("- 성장 방향 제안")

st.sidebar.divider()
st.sidebar.caption("Created by 장아영")

nickname_input = st.text_input(
    "구단주명을 입력하세요",
    placeholder="분석할 구단주명을 입력하세요"
)

analyze_button = st.button("분석하기", type="primary")

if analyze_button:
    nickname = nickname_input.strip()

    if not nickname:
        st.warning("구단주명을 입력해주세요.")
        st.stop()

    try:
        with st.spinner("매치 데이터를 불러오는 중입니다."):
            ouid = get_ouid(nickname)

            if not ouid:
                st.warning("해당 구단주명을 찾을 수 없습니다. 구단주명을 다시 확인해주세요.")
                st.stop()

            matchtype_name, match_ids = find_best_matchtype(ouid)

            if not match_ids:
                st.warning("최근 분석 가능한 경기 데이터를 찾지 못했습니다.")
                st.stop()

            df = build_match_dataframe(
                ouid=ouid,
                nickname=nickname,
                matchtype_name=matchtype_name,
                match_ids=match_ids
            )

            if df is None or df.empty:
                st.warning("경기 상세 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
                st.stop()

        render_dashboard(df)

    except Exception:
        st.error("앱 실행 중 오류가 발생했습니다.")
        st.caption("외부 API 응답 오류 또는 일시적인 서버 문제일 수 있습니다.")
