/**
 * 유치원콕 (유치원 비교분석 웹앱 MVP) 메인 로직
 * - 쇼핑몰형 지역 + 다중 조건 필터링
 * - 규칙 기반(Rule-based) 스마트 공시 분석 및 맞춤 가중치 랭킹 (LLM API 비용 0원)
 * - 다자간 한눈에 비교 테이블 (우위 항목 자동 👑 하이라이트)
 * - 쿠팡 파트너스 인피드 & 비교 완료 하단 큐레이션
 */

const PAGE_SIZE = 24;

const state = {
  activeTab: "explore",
  sido: "전체",
  sigungu: "전체",
  dong: "전체",
  searchQuery: "",
  conditions: new Set(),
  sortBy: "score",
  visibleLimit: PAGE_SIZE,
  compareWeightMode: "balanced", // balanced | cost | care | teacher | facility
  favorites: new Set(),
  compareList: []
};

// 파생 지표 사전 계산 (교사 1인당 원아 수, 4년+ 장기근속 비율, 정원 충족률 등)
const KG_MAP = new Map();
KINDERGARTEN_DATA.forEach((kg) => {
  const regT = Math.max(kg.teachers.regularTeacher || 1, 1);
  const totT = Math.max(kg.teachers.total || 1, 1);
  const capT = Math.max(kg.capacityTotal || 1, 1);
  const ratio = +(kg.enrolledTotal / regT).toFixed(1);
  const veteranPct = Math.min(100, Math.round((kg.teachers.over4yr / totT) * 100));
  const fillRate = Math.min(150, Math.round((kg.enrolledTotal / capT) * 100));
  const isPublic = kg.establishType.includes("국공립");
  const isDanseol = kg.establishType.includes("단설");
  kg._derived = {
    ratio,
    veteranPct,
    fillRate,
    isPublic,
    isDanseol
  };
  kg._derived.score = computeWeightedScore(kg, "balanced");
  kg._derived.smartSummary = buildSmartSummary(kg);
  KG_MAP.set(kg.id, kg);
});

// 초기 로컬스토리지 복원 (첫 방문 시 바로 비교 체험이 가능하도록 대표 국공립 단설 vs 사립 2곳 기본 탑재)
function getDefaultComparePair() {
  const pub = KINDERGARTEN_DATA.find((k) => k._derived.isDanseol && k.operation.hasBus && k.enrolledTotal >= 100) || KINDERGARTEN_DATA[0];
  const priv = KINDERGARTEN_DATA.find((k) => !k._derived.isPublic && k.operation.hasBus && k.enrolledTotal >= 120) || KINDERGARTEN_DATA[1];
  return [pub?.id, priv?.id].filter(Boolean);
}

function loadPersistedState() {
  try {
    const savedFavs = JSON.parse(localStorage.getItem("kg_cock_favs") || "null");
    if (Array.isArray(savedFavs)) {
      savedFavs.forEach((id) => {
        if (KG_MAP.has(id)) state.favorites.add(id);
      });
    }
    const savedCmp = JSON.parse(localStorage.getItem("kg_cock_cmp") || "null");
    const validCmp = Array.isArray(savedCmp) ? savedCmp.filter((id) => KG_MAP.has(id)).slice(0, 4) : [];
    if (validCmp.length > 0) {
      state.compareList = validCmp;
    } else {
      state.compareList = getDefaultComparePair();
    }
  } catch (e) {
    state.compareList = getDefaultComparePair();
  }
}

function savePersistedState() {
  try {
    localStorage.setItem("kg_cock_favs", JSON.stringify([...state.favorites]));
    localStorage.setItem("kg_cock_cmp", JSON.stringify(state.compareList));
  } catch (e) {}
}

/**
 * [핵심 기능] LLM 호출 없이 공시 수치로 즉시 생성하는 규칙 기반(Rule-based) 스마트 분석 코멘트
 */
function buildSmartSummary(kg) {
  const d = kg._derived;
  const points = [];

  if (d.isDanseol) {
    points.push("단독건물 국공립 단설(무상지원)");
  } else if (d.isPublic) {
    points.push("국공립 병설(유아학비·급식 지원)");
  }

  if (d.ratio > 0 && d.ratio <= 10.5) {
    points.push(`교사 1인당 ${d.ratio}명 세심한 케어`);
  }

  if (d.veteranPct >= 50) {
    points.push(`4년+ 장기근속 교사 ${d.veteranPct}%`);
  }

  if (kg.operation.hasBus) {
    points.push(`통학버스 ${kg.operation.busCount}대 운행`);
  }

  if (kg.operation.afterSchoolEndHour >= 19.0) {
    const endStr = kg.operation.afterSchoolTime.split("~")[1]?.trim() || "19:00";
    points.push(`방과후 돌봄 ${endStr}까지`);
  }

  if (kg.facilitySafety.indoorGymSqm >= 100) {
    points.push(`실내체육장 ${kg.facilitySafety.indoorGymSqm}㎡ 보유`);
  }

  if (points.length === 0) {
    points.push(`정원 ${kg.capacityTotal}명 · 방과후 과정 운영`);
  }

  return points.slice(0, 3).join(" · ");
}

/**
 * 학부모 우선순위 가중치별 100점 만점 환산 점수 계산기
 */
function computeWeightedScore(kg, mode = "balanced") {
  const d = kg._derived;
  // 개별 영역 점수 (0 ~ 100)
  const costScore = Math.max(20, 100 - Math.round(kg.cost.monthlyTotal / 3800));
  const careScore =
    (kg.operation.hasBus ? 40 : 10) +
    (kg.operation.afterSchoolEndHour >= 19.5 ? 40 : 25) +
    (kg.operation.vacationCare.includes("상시") || kg.operation.vacationCare.includes("온종일") ? 20 : 12);
  const teacherScore = Math.min(
    100,
    Math.round(Math.max(0, (16 - d.ratio) * 6.5) + d.veteranPct * 0.45)
  );
  const facilityScore = Math.min(
    100,
    Math.round(
      kg.facilitySafety.perChildAreaSqm * 14 +
        (kg.facilitySafety.indoorGymSqm >= 180 ? 25 : 15) +
        (kg.facilitySafety.cctvTotal >= 28 ? 25 : 15)
    )
  );

  const weights = {
    balanced: { cost: 0.25, care: 0.25, teacher: 0.3, facility: 0.2 },
    cost: { cost: 0.6, care: 0.15, teacher: 0.15, facility: 0.1 },
    care: { cost: 0.1, care: 0.6, teacher: 0.15, facility: 0.15 },
    teacher: { cost: 0.1, care: 0.15, teacher: 0.6, facility: 0.15 },
    facility: { cost: 0.1, care: 0.15, teacher: 0.15, facility: 0.6 }
  }[mode] || { cost: 0.25, care: 0.25, teacher: 0.3, facility: 0.2 };

  return Math.round(
    costScore * weights.cost +
      careScore * weights.care +
      teacherScore * weights.teacher +
      facilityScore * weights.facility
  );
}

function formatWon(amount) {
  if (!amount || amount === 0) return "0원(무상)";
  if (amount >= 10000) {
    const man = (amount / 10000).toFixed(amount % 10000 === 0 ? 0 : 1);
    return `약 ${man}만원`;
  }
  return `${amount.toLocaleString("ko-KR")}원`;
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ================= 지역 드롭다운 및 수도권 퀵탭 초기화 ================= */
function syncCapitalQuickTabs() {
  const tabsWrap = document.getElementById("capital-quick-tabs");
  if (!tabsWrap) return;
  const labels = [
    ["전체", "수도권 전체", KINDERGARTEN_DATA.length],
    ["서울특별시", "서울", KINDERGARTEN_DATA.filter((k) => k.sido === "서울특별시").length],
    ["경기도", "경기", KINDERGARTEN_DATA.filter((k) => k.sido === "경기도").length],
    ["인천광역시", "인천", KINDERGARTEN_DATA.filter((k) => k.sido === "인천광역시").length]
  ];
  tabsWrap.innerHTML = labels
    .map(
      ([val, label, cnt]) => `
      <button
        class="filter-chip ${state.sido === val ? "active" : ""}"
        data-sido="${escapeHtml(val)}"
        onclick="onSidoChange('${escapeHtml(val)}')"
      >${escapeHtml(label)} <span style="opacity:0.8;font-weight:600;">(${cnt})</span></button>
    `
    )
    .join("");
}

function initRegionSelectors() {
  const sidos = ["전체", "서울특별시", "경기도", "인천광역시"];
  const sidoEl = document.getElementById("sel-sido");
  sidoEl.innerHTML = sidos
    .map((s) => `<option value="${escapeHtml(s)}" ${s === state.sido ? "selected" : ""}>${s === "전체" ? "수도권 시/도 전체" : escapeHtml(s)}</option>`)
    .join("");
  syncCapitalQuickTabs();
  updateSigunguSelector();
}

function updateSigunguSelector() {
  const pool = state.sido === "전체" ? KINDERGARTEN_DATA : KINDERGARTEN_DATA.filter((k) => k.sido === state.sido);
  const uniqueSgs = [...new Set(pool.map((k) => k.sigungu))].sort((a, b) => a.localeCompare(b, "ko"));
  const sigungus = ["전체", ...uniqueSgs];
  if (!sigungus.includes(state.sigungu)) state.sigungu = "전체";

  const sgEl = document.getElementById("sel-sigungu");
  sgEl.innerHTML = sigungus
    .map((sg) => `<option value="${escapeHtml(sg)}" ${sg === state.sigungu ? "selected" : ""}>${sg === "전체" ? `시/군/구 전체 (${uniqueSgs.length})` : escapeHtml(sg)}</option>`)
    .join("");
  updateDongSelector();
}

function updateDongSelector() {
  let pool = KINDERGARTEN_DATA;
  if (state.sido !== "전체") pool = pool.filter((k) => k.sido === state.sido);
  if (state.sigungu !== "전체") pool = pool.filter((k) => k.sigungu === state.sigungu);
  const uniqueDongs = [...new Set(pool.map((k) => k.dong))].sort((a, b) => a.localeCompare(b, "ko"));
  const dongs = ["전체", ...uniqueDongs];
  if (!dongs.includes(state.dong)) state.dong = "전체";

  const dongEl = document.getElementById("sel-dong");
  dongEl.innerHTML = dongs
    .map((d) => `<option value="${escapeHtml(d)}" ${d === state.dong ? "selected" : ""}>${d === "전체" ? `읍/면/동·도로 전체 (${uniqueDongs.length})` : escapeHtml(d)}</option>`)
    .join("");
}

function onSidoChange(val) {
  state.sido = val;
  state.sigungu = "전체";
  state.dong = "전체";
  state.visibleLimit = PAGE_SIZE;
  const sidoEl = document.getElementById("sel-sido");
  if (sidoEl) sidoEl.value = val;
  syncCapitalQuickTabs();
  updateSigunguSelector();
  renderExploreList();
}

function onSigunguChange(val) {
  state.sigungu = val;
  state.dong = "전체";
  state.visibleLimit = PAGE_SIZE;
  updateDongSelector();
  renderExploreList();
}

function onDongChange(val) {
  state.dong = val;
  state.visibleLimit = PAGE_SIZE;
  renderExploreList();
}

function onSearchInput(val) {
  state.searchQuery = val.trim();
  state.visibleLimit = PAGE_SIZE;
  renderExploreList();
}

function onSortChange(val) {
  state.sortBy = val;
  state.visibleLimit = PAGE_SIZE;
  renderExploreList();
}

function toggleCondition(key) {
  if (state.conditions.has(key)) {
    state.conditions.delete(key);
  } else {
    // 국공립만 / 단설만 / 사립만은 상호 배타 선택 처리
    if (key === "public" || key === "danseol") state.conditions.delete("private");
    if (key === "private") {
      state.conditions.delete("public");
      state.conditions.delete("danseol");
    }
    state.conditions.add(key);
  }
  state.visibleLimit = PAGE_SIZE;
  syncConditionChipsUI();
  renderExploreList();
}

function syncConditionChipsUI() {
  document.querySelectorAll("#condition-chips .filter-chip").forEach((btn) => {
    const f = btn.getAttribute("data-filter");
    btn.classList.toggle("active", state.conditions.has(f));
  });
}

function resetAllFilters() {
  state.sido = "전체";
  state.sigungu = "전체";
  state.dong = "전체";
  state.searchQuery = "";
  state.conditions.clear();
  state.sortBy = "score";
  state.visibleLimit = PAGE_SIZE;
  const searchEl = document.getElementById("search-input");
  if (searchEl) searchEl.value = "";
  const sortEl = document.getElementById("sort-select");
  if (sortEl) sortEl.value = "score";
  initRegionSelectors();
  syncConditionChipsUI();
  renderExploreList();
  showToast("모든 검색 필터를 초기화했어요");
}

/* ================= 필터링 및 정렬 로직 ================= */
function getFilteredKindergartens() {
  let list = KINDERGARTEN_DATA.filter((kg) => {
    if (state.sido !== "전체" && kg.sido !== state.sido) return false;
    if (state.sigungu !== "전체" && kg.sigungu !== state.sigungu) return false;
    if (state.dong !== "전체" && kg.dong !== state.dong) return false;

    if (state.conditions.has("public") && !kg._derived.isPublic) return false;
    if (state.conditions.has("danseol") && !kg._derived.isDanseol) return false;
    if (state.conditions.has("private") && kg._derived.isPublic) return false;
    if (state.conditions.has("bus") && !kg.operation.hasBus) return false;
    if (state.conditions.has("lateCare") && kg.operation.afterSchoolEndHour < 19.0) return false;
    if (state.conditions.has("lowCost") && kg.cost.monthlyTotal > 50000) return false;
    if (state.conditions.has("goodRatio") && (kg._derived.ratio <= 0 || kg._derived.ratio > 11.0)) return false;
    if (state.conditions.has("veteran") && kg._derived.veteranPct < 50) return false;
    if (state.conditions.has("gym") && kg.facilitySafety.indoorGymSqm <= 0) return false;
    if (state.conditions.has("special") && (!kg.classes.special || kg.classes.special.count <= 0)) return false;

    if (state.searchQuery) {
      const q = state.searchQuery.toLowerCase();
      const target = [
        kg.name,
        kg.sido,
        kg.sigungu,
        kg.dong,
        kg.address,
        kg.establishType,
        kg.eduOffice || "",
        ...kg.specialPrograms,
        ...kg.tags
      ]
        .join(" ")
        .toLowerCase();
      if (!target.includes(q)) return false;
    }
    return true;
  });

  list.sort((a, b) => {
    switch (state.sortBy) {
      case "costAsc":
        return a.cost.monthlyTotal - b.cost.monthlyTotal || b._derived.score - a._derived.score;
      case "ratioAsc":
        return (a._derived.ratio || 99) - (b._derived.ratio || 99);
      case "veteranDesc":
        return b._derived.veteranPct - a._derived.veteranPct;
      case "capacityDesc":
        return b.capacityTotal - a.capacityTotal;
      case "score":
      default:
        return b._derived.score - a._derived.score;
    }
  });

  return list;
}

/* ================= 카드 및 쿠팡 파트너스 렌더링 ================= */
function renderKgCard(kg) {
  const d = kg._derived;
  const inCmp = state.compareList.includes(kg.id);
  const isFav = state.favorites.has(kg.id);
  const afterEnd = kg.operation.afterSchoolTime.split("~")[1]?.trim() || "-";

  return `
    <article class="kg-card ${inCmp ? "in-compare" : ""}">
      <div class="kg-card-top">
        <div>
          <div class="badge-row">
            <span class="est-badge ${d.isPublic ? "public" : "private"}">${escapeHtml(kg.establishType)}</span>
            <span class="tag-badge">${kg.operation.hasBus ? `🚌 셔틀 ${kg.operation.busCount}대` : "🚶 도보등원"}</span>
            <span class="tag-badge">⏰ 돌봄 ${escapeHtml(afterEnd)}</span>
            ${kg.specialPrograms.slice(0, 2).map((p) => `<span class="tag-badge">#${escapeHtml(p)}</span>`).join("")}
          </div>
          <button class="kg-title-btn" onclick="openDetailModal('${kg.id}')">
            <h3 class="kg-name">${escapeHtml(kg.name)}</h3>
            <p class="kg-addr">📍 ${escapeHtml(kg.sido)} ${escapeHtml(kg.sigungu)} (${escapeHtml(kg.dong)}) · ${escapeHtml(kg.address)}</p>
          </button>
        </div>
        <button
          class="fav-icon-btn ${isFav ? "active" : ""}"
          onclick="toggleFavorite('${kg.id}')"
          aria-label="찜하기"
          title="관심 유치원 찜하기"
        >
          ${isFav ? "❤️" : "🤍"}
        </button>
      </div>

      <!-- 규칙 기반 스마트 요약 박스 -->
      <div class="smart-insight-box">
        <div class="smart-insight-title">✨ 공시 데이터 핵심 요약 (종합 ${d.score}점)</div>
        <div>${escapeHtml(d.smartSummary)}</div>
      </div>

      <!-- 4대 핵심 지표 -->
      <div class="kg-metrics-grid">
        <div class="metric-cell">
          <span class="metric-label">유아학비·부담</span>
          <strong class="metric-val highlight">${d.isPublic ? "국공립 무상" : "유아학비 지원"}</strong>
        </div>
        <div class="metric-cell">
          <span class="metric-label">교사 1명당</span>
          <strong class="metric-val">1 : ${d.ratio}명</strong>
        </div>
        <div class="metric-cell">
          <span class="metric-label">4년+ 베테랑교사</span>
          <strong class="metric-val">${d.veteranPct}%</strong>
        </div>
        <div class="metric-cell">
          <span class="metric-label">현원 / 정원</span>
          <strong class="metric-val">${kg.enrolledTotal}/${kg.capacityTotal}명</strong>
        </div>
      </div>

      <div class="kg-card-actions">
        <button class="btn" onclick="openDetailModal('${kg.id}')">📊 상세 공시 보기</button>
        <button
          class="btn ${inCmp ? "primary" : "outline-primary"}"
          onclick="toggleCompare('${kg.id}')"
        >
          ${inCmp ? "✓ 비교함에 담김" : "+ 비교 담기"}
        </button>
      </div>
    </article>
  `;
}

function normalizeCoupangUrl(rawUrl) {
  let u = String(rawUrl || "").trim();
  if (!u) return "#";
  // 위젯 전체 주소나 linkUrl=... 형태를 붙여넣은 경우에도 자동 추출 및 디코딩
  if (u.includes("linkUrl=")) {
    const m = u.match(/linkUrl=([^&]+)/);
    if (m && m[1]) u = m[1];
  }
  if (u.includes("&productImage=")) {
    u = u.split("&productImage=")[0];
  }
  if (u.includes("%2F") || u.includes("%3F") || u.includes("%3D")) {
    try {
      u = decodeURIComponent(u);
    } catch (e) {}
  }
  const idx = u.indexOf("link.coupang.com");
  if (idx >= 0 && !u.startsWith("http")) {
    u = "https://" + u.slice(idx);
  }
  return u;
}

function renderCoupangCurationWidget(titleOverride) {
  const b = COUPANG_CURATION.inFeedBanner;
  return `
    <aside class="coupang-card" aria-label="등원 준비물 추천">
      <div class="cp-header">
        <span class="cp-badge">${escapeHtml(b.badge)}</span>
        <span class="cp-ad-tag">쿠팡 파트너스 추천</span>
      </div>
      <h4 class="cp-title">${escapeHtml(titleOverride || b.title)}</h4>
      <p class="cp-sub">${escapeHtml(b.subtitle)}</p>
      <div class="cp-items-grid">
        ${COUPANG_CURATION.items
          .map(
            (item) => `
          <a class="cp-item" href="${escapeHtml(normalizeCoupangUrl(item.url))}" target="_blank" rel="noopener">
            <div>
              <div class="cp-item-top">
                ${
                  item.image
                    ? `<img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.name)}" style="width:44px;height:44px;object-fit:cover;border-radius:8px;border:1px solid #f1f5f9;" />`
                    : `<span class="cp-emoji">${item.emoji}</span>`
                }
                <span class="cp-item-badge">${escapeHtml(item.badge)}</span>
              </div>
              <div class="cp-item-name">${escapeHtml(item.name)}</div>
            </div>
            <div style="margin-top: 6px;">
              <div class="cp-item-price">${escapeHtml(item.price)}</div>
              <div class="cp-item-rating">★ ${escapeHtml(item.rating)}</div>
            </div>
          </a>
        `
          )
          .join("")}
      </div>
      <p class="cp-disclaimer">${escapeHtml(COUPANG_CURATION.disclaimer)}</p>
    </aside>
  `;
}

function loadMoreCards() {
  state.visibleLimit += PAGE_SIZE;
  renderExploreList();
}

function renderExploreList() {
  const list = getFilteredKindergartens();
  const countEl = document.getElementById("result-count-text");
  if (countEl) {
    countEl.innerHTML = `조건에 맞는 유치원 <span>${list.length.toLocaleString("ko-KR")}</span>곳`;
  }

  const container = document.getElementById("kg-card-list");
  if (!container) return;

  if (list.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div style="font-size: 2.2rem; margin-bottom: 8px;">🔍</div>
        <strong style="display: block; font-size: 1rem; color: var(--text); margin-bottom: 4px;">선택하신 조건에 맞는 유치원이 없어요</strong>
        <p style="font-size: 0.84rem; margin: 0 0 14px;">조건 칩을 일부 해제하거나 전체 지역으로 넓혀보세요.</p>
        <button class="btn primary" style="max-width: 180px; margin: 0 auto;" onclick="resetAllFilters()">필터 초기화하기</button>
      </div>
    `;
    return;
  }

  const visibleSlice = list.slice(0, state.visibleLimit);
  const htmlParts = [];
  visibleSlice.forEach((kg, idx) => {
    htmlParts.push(renderKgCard(kg));
    // 2번째 카드 바로 뒤에 네이티브 인피드 쿠팡 파트너스 큐레이션 배치
    if (idx === 1) {
      htmlParts.push(renderCoupangCurationWidget());
    }
  });
  if (visibleSlice.length < 2) {
    htmlParts.push(renderCoupangCurationWidget());
  }

  if (list.length > state.visibleLimit) {
    const remaining = list.length - state.visibleLimit;
    htmlParts.push(`
      <div style="text-align: center; margin: 16px 0 8px;">
        <button
          class="btn outline-primary"
          style="width: 100%; max-width: 360px; margin: 0 auto; font-weight: 800;"
          onclick="loadMoreCards()"
        >
          👇 유치원 더 보기 (+${Math.min(PAGE_SIZE, remaining)}곳 · 현재 ${visibleSlice.length.toLocaleString("ko-KR")}/${list.length.toLocaleString("ko-KR")}곳)
        </button>
      </div>
    `);
  }

  container.innerHTML = htmlParts.join("");
}

/* ================= 찜하기 및 비교함 상태 제어 ================= */
function toggleFavorite(id) {
  if (state.favorites.has(id)) {
    state.favorites.delete(id);
    showToast("찜 목록에서 제외했어요");
  } else {
    state.favorites.add(id);
    showToast("❤️ 관심 유치원에 찜했어요!");
  }
  savePersistedState();
  updateBadgesAndBars();
  renderExploreList();
  if (state.activeTab === "favorites") renderFavoritesTab();
}

function toggleCompare(id) {
  const idx = state.compareList.indexOf(id);
  if (idx >= 0) {
    state.compareList.splice(idx, 1);
    showToast("비교함에서 제외했어요");
  } else {
    if (state.compareList.length >= 4) {
      showToast("비교함에는 최대 4곳까지 담을 수 있어요");
      return;
    }
    state.compareList.push(id);
    showToast(`⚖️ 비교함에 담았어요 (${state.compareList.length}/4)`);
  }
  savePersistedState();
  updateBadgesAndBars();
  renderExploreList();
  if (state.activeTab === "compare") renderCompareTab();
  if (state.activeTab === "favorites") renderFavoritesTab();
}

function clearCompareList() {
  state.compareList = [];
  savePersistedState();
  updateBadgesAndBars();
  renderExploreList();
  if (state.activeTab === "compare") renderCompareTab();
  showToast("비교함을 비웠어요");
}

function updateBadgesAndBars() {
  const favCount = state.favorites.size;
  const cmpCount = state.compareList.length;

  document.getElementById("header-fav-count").textContent = favCount;
  document.getElementById("header-cmp-count").textContent = cmpCount;

  const tabFavBadge = document.getElementById("tab-fav-badge");
  if (tabFavBadge) {
    tabFavBadge.style.display = favCount > 0 ? "inline-flex" : "none";
    tabFavBadge.textContent = favCount;
  }

  const tabCmpBadge = document.getElementById("tab-cmp-badge");
  if (tabCmpBadge) {
    tabCmpBadge.style.display = cmpCount > 0 ? "inline-flex" : "none";
    tabCmpBadge.textContent = cmpCount;
  }

  // 하단 플로팅 비교바 업데이트
  const bar = document.getElementById("floating-cmp-bar");
  const chipsContainer = document.getElementById("floating-cmp-chips");
  const statusEl = document.getElementById("floating-cmp-status");

  if (cmpCount > 0 && state.activeTab === "explore") {
    bar.style.display = "block";
    chipsContainer.innerHTML = state.compareList
      .map((id) => {
        const k = KG_MAP.get(id);
        return `<span class="cmp-mini-chip">${escapeHtml(k.name)} <button onclick="toggleCompare('${id}')" aria-label="제거">✕</button></span>`;
      })
      .join("");
    statusEl.textContent =
      cmpCount >= 2
        ? `${cmpCount}곳 선택됨 · 지금 바로 대조해 보세요!`
        : `1곳 선택됨 · 1곳만 더 담으면 비교표가 열려요`;
  } else {
    bar.style.display = "none";
  }
}

/* ================= 다자간 비교 분석 렌더링 (모달 & 탭 공용) ================= */
function buildCompareHTML(isModal = false) {
  const kgs = state.compareList.map((id) => KG_MAP.get(id)).filter(Boolean);

  if (kgs.length < 2) {
    return `
      ${isModal ? `<div class="sheet-header"><h2 class="sheet-title">⚖️ 유치원 한눈에 비교</h2><button class="close-sheet-btn" onclick="closeModal()">닫기 ✕</button></div>` : ""}
      <div class="empty-state">
        <div style="font-size: 2.4rem; margin-bottom: 8px;">⚖️</div>
        <strong style="display: block; font-size: 1.02rem; color: var(--text); margin-bottom: 6px;">비교할 유치원을 2곳 이상 담아주세요 (현재 ${kgs.length}곳)</strong>
        <p style="font-size: 0.84rem; margin: 0 0 14px;">메인 목록에서 [+ 비교 담기] 버튼을 누르면 최대 4곳까지 나란히 비교할 수 있어요.</p>
        <button class="btn primary" style="max-width: 220px; margin: 0 auto;" onclick="closeModal(); switchTab('explore');">유치원 고르러 가기</button>
      </div>
    `;
  }

  // 가중치 모드별 실시간 순위 계산
  const ranked = kgs
    .map((k) => ({
      kg: k,
      score: computeWeightedScore(k, state.compareWeightMode)
    }))
    .sort((a, b) => b.score - a.score);

  const weightModes = [
    { id: "balanced", label: "✨ 종합 균형" },
    { id: "cost", label: "💸 비용 절약 최우선" },
    { id: "care", label: "🚌 맞벌이·돌봄 최우선" },
    { id: "teacher", label: "👩‍🏫 교사 비율·근속" },
    { id: "facility", label: "🏃 시설·안전 최우선" }
  ];

  // 우위 셀 판정을 위한 최고값 계산
  const minCost = Math.min(...kgs.map((k) => k.cost.monthlyTotal));
  const minRatio = Math.min(...kgs.map((k) => k._derived.ratio));
  const maxVeteran = Math.max(...kgs.map((k) => k._derived.veteranPct));
  const maxArea = Math.max(...kgs.map((k) => k.facilitySafety.perChildAreaSqm));
  const maxAfterHour = Math.max(...kgs.map((k) => k.operation.afterSchoolEndHour));
  const maxBus = Math.max(...kgs.map((k) => k.operation.busCount));
  const maxCctv = Math.max(...kgs.map((k) => k.facilitySafety.cctvTotal));

  return `
    ${
      isModal
        ? `<div class="sheet-header">
            <h2 class="sheet-title">⚖️ 유치원 다자간 비교 분석 (${kgs.length}곳)</h2>
            <button class="close-sheet-btn" onclick="closeModal()">닫기 ✕</button>
          </div>`
        : `<h2 style="font-size: 1.2rem; font-weight: 800; margin: 4px 0 10px;">⚖️ 유치원 다자간 비교 분석 (${kgs.length}곳)</h2>`
    }

    <!-- 1. 내 기준 맞춤 가중치 랭킹 -->
    <div class="rank-box">
      <div style="font-size: 0.92rem; font-weight: 800; margin-bottom: 4px;">🎯 우리 집 최우선 기준을 선택해 보세요</div>
      <p style="font-size: 0.78rem; color: var(--text-sub); margin: 0 0 10px;">
        선택한 우선순위에 맞춰 유치원알리미 공시 데이터 가중치 점수가 즉시 재계산됩니다.
      </p>
      <div class="chip-group" style="margin-bottom: 12px;">
        ${weightModes
          .map(
            (m) => `
          <button
            class="filter-chip ${state.compareWeightMode === m.id ? "active" : ""}"
            onclick="setCompareWeightMode('${m.id}', ${isModal})"
          >${m.label}</button>
        `
          )
          .join("")}
      </div>

      ${ranked
        .map(
          (item, i) => `
        <div class="rank-item ${i === 0 ? "top-winner" : ""}">
          <div class="rank-num">${i === 0 ? "👑" : `${i + 1}위`}</div>
          <div style="flex: 1; min-width: 0;">
            <div style="display: flex; justify-content: space-between; align-items: baseline;">
              <strong style="font-size: 0.94rem;">${escapeHtml(item.kg.name)}</strong>
              <span style="font-size: 0.85rem; font-weight: 800; color: var(--primary);">${item.score}점</span>
            </div>
            <div class="rank-bar-track">
              <div class="rank-bar-fill" style="width: ${item.score}%;"></div>
            </div>
            <div style="font-size: 0.76rem; color: var(--text-sub);">${escapeHtml(item.kg._derived.smartSummary)}</div>
          </div>
        </div>
      `
        )
        .join("")}
    </div>

    <!-- 2. 유치원알리미 공시항목 정밀 대조표 -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin: 16px 2px 8px;">
      <strong style="font-size: 0.96rem;">📑 유치원알리미 공시항목 1:1 대조표</strong>
      <span style="font-size: 0.75rem; color: var(--green-text); font-weight: 700;">👑 초록색 칸 = 비교 우위 항목</span>
    </div>

    <div class="cmp-table-wrap">
      <table class="cmp-table">
        <thead>
          <tr>
            <th>비교 항목</th>
            ${kgs
              .map(
                (k) => `
              <th>
                <span class="est-badge ${k._derived.isPublic ? "public" : "private"}" style="display:inline-block; margin-bottom:4px;">${escapeHtml(k.establishType)}</span>
                <div style="font-size: 0.92rem; font-weight: 800;">${escapeHtml(k.name)}</div>
                <button class="reset-btn" style="margin-top:4px;" onclick="toggleCompare('${k.id}'); ${isModal ? "openCompareModal()" : "renderCompareTab()"}">비교에서 빼기</button>
              </th>
            `
              )
              .join("")}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th>위치 (동)</th>
            ${kgs.map((k) => `<td>${escapeHtml(k.sigungu)} <b>${escapeHtml(k.dong)}</b></td>`).join("")}
          </tr>
          <tr>
            <th>월 실부담금</th>
            ${kgs
              .map((k) => {
                const best = k.cost.monthlyTotal === minCost;
                return `<td class="${best ? "best-cell" : ""}">${best ? "👑 " : ""}${formatWon(k.cost.monthlyTotal)}<br><small style="font-weight:400; color:var(--text-sub);">${escapeHtml(k.cost.note)}</small></td>`;
              })
              .join("")}
          </tr>
          <tr>
            <th>교사 1인당 원아</th>
            ${kgs
              .map((k) => {
                const best = k._derived.ratio === minRatio;
                return `<td class="${best ? "best-cell" : ""}">${best ? "👑 " : ""}1 : ${k._derived.ratio}명<br><small style="font-weight:400;">담임·보직교사 ${k.teachers.regularTeacher}명</small></td>`;
              })
              .join("")}
          </tr>
          <tr>
            <th>4년+ 장기근속</th>
            ${kgs
              .map((k) => {
                const best = k._derived.veteranPct === maxVeteran;
                return `<td class="${best ? "best-cell" : ""}">${best ? "👑 " : ""}${k._derived.veteranPct}% (${k.teachers.over4yr}/${k.teachers.total}명)</td>`;
              })
              .join("")}
          </tr>
          <tr>
            <th>현원 / 정원</th>
            ${kgs
              .map(
                (k) =>
                  `<td>${k.enrolledTotal} / ${k.capacityTotal}명<br><small style="color:var(--text-sub);">충족률 ${k._derived.fillRate}%</small></td>`
              )
              .join("")}
          </tr>
          <tr>
            <th>연령별 정원</th>
            ${kgs
              .map(
                (k) =>
                  `<td><small>만3세: ${k.classes.age3.capacity}명 (${k.classes.age3.count}반)<br>만4세: ${k.classes.age4.capacity}명 (${k.classes.age4.count}반)<br>만5세: ${k.classes.age5.capacity}명 (${k.classes.age5.count}반)</small></td>`
              )
              .join("")}
          </tr>
          <tr>
            <th>방과후 돌봄</th>
            ${kgs
              .map((k) => {
                const best = k.operation.afterSchoolEndHour === maxAfterHour;
                return `<td class="${best ? "best-cell" : ""}">${best ? "👑 " : ""}${escapeHtml(k.operation.afterSchoolTime)}<br><small style="font-weight:400;">${escapeHtml(k.operation.vacationCare)}</small></td>`;
              })
              .join("")}
          </tr>
          <tr>
            <th>통학버스</th>
            ${kgs
              .map((k) => {
                const best = k.operation.busCount === maxBus && maxBus > 0;
                return `<td class="${best ? "best-cell" : ""}">${k.operation.hasBus ? `${best ? "👑 " : ""}운행 (${k.operation.busCount}대)` : "미운행 (도보등원)"}</td>`;
              })
              .join("")}
          </tr>
          <tr>
            <th>1인당 교실면적</th>
            ${kgs
              .map((k) => {
                const best = k.facilitySafety.perChildAreaSqm === maxArea;
                return `<td class="${best ? "best-cell" : ""}">${best ? "👑 " : ""}${k.facilitySafety.perChildAreaSqm}㎡<br><small style="font-weight:400;">실내체육장 ${k.facilitySafety.indoorGymSqm}㎡</small></td>`;
              })
              .join("")}
          </tr>
          <tr>
            <th>급식 운영</th>
            ${kgs.map((k) => `<td>${escapeHtml(k.operation.mealType)}</td>`).join("")}
          </tr>
          <tr>
            <th>CCTV / 안전점검</th>
            ${kgs
              .map((k) => {
                const best = k.facilitySafety.cctvTotal === maxCctv;
                return `<td class="${best ? "best-cell" : ""}">${best ? "👑 " : ""}CCTV ${k.facilitySafety.cctvTotal}대<br><small style="font-weight:400;">소방·가스·놀이시설 적합</small></td>`;
              })
              .join("")}
          </tr>
          <tr>
            <th>특색 프로그램</th>
            ${kgs
              .map((k) => `<td>${k.specialPrograms.map((p) => `<span class="tag-badge" style="display:inline-block;margin:2px;">#${escapeHtml(p)}</span>`).join("")}</td>`)
              .join("")}
          </tr>
          <tr>
            <th>문의 전화</th>
            ${kgs.map((k) => `<td><a href="tel:${escapeHtml(k.phone)}" style="color:var(--primary);font-weight:800;">📞 ${escapeHtml(k.phone)}</a></td>`).join("")}
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 3. 비교 완료 후 쿠팡 파트너스 전환 슬롯 -->
    ${renderCoupangCurationWidget("💡 유치원 비교가 끝났다면? 입학 전 미리 준비하는 등원 필수템")}
  `;
}

function setCompareWeightMode(mode, isModal) {
  state.compareWeightMode = mode;
  if (isModal) {
    openCompareModal();
  } else {
    renderCompareTab();
  }
}

function openCompareModal() {
  if (state.compareList.length < 2) {
    showToast("비교할 유치원을 2곳 이상 담아주세요!");
    switchTab("compare");
    return;
  }
  const backdrop = document.getElementById("modal-backdrop");
  const content = document.getElementById("modal-sheet-content");
  content.innerHTML = buildCompareHTML(true);
  backdrop.classList.add("open");
}

function renderCompareTab() {
  const el = document.getElementById("tab-compare-content");
  if (el) el.innerHTML = buildCompareHTML(false);
}

/* ================= 유치원 상세 모달 ================= */
function openDetailModal(id) {
  const kg = KG_MAP.get(id);
  if (!kg) return;
  const d = kg._derived;
  const inCmp = state.compareList.includes(kg.id);
  const isFav = state.favorites.has(kg.id);

  const backdrop = document.getElementById("modal-backdrop");
  const content = document.getElementById("modal-sheet-content");

  content.innerHTML = `
    <div class="sheet-header">
      <h2 class="sheet-title">🏫 유치원 상세 공시 리포트</h2>
      <button class="close-sheet-btn" onclick="closeModal()">닫기 ✕</button>
    </div>

    <div class="detail-section" style="background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%); border-color: var(--primary-border);">
      <div class="badge-row">
        <span class="est-badge ${d.isPublic ? "public" : "private"}">${escapeHtml(kg.establishType)}</span>
        <span class="tag-badge">설립 ${kg.establishedYear}년</span>
        <span class="tag-badge">정원충족률 ${d.fillRate}%</span>
      </div>
      <h3 style="font-size: 1.35rem; font-weight: 800; margin: 6px 0 4px;">${escapeHtml(kg.name)}</h3>
      <p style="font-size: 0.86rem; color: var(--text-sub); margin: 0 0 12px;">📍 ${escapeHtml(kg.address)}</p>

      <div class="smart-insight-box" style="margin: 0 0 12px;">
        <div class="smart-insight-title">✨ 공시 데이터 기반 핵심 진단</div>
        <div>${escapeHtml(d.smartSummary)}</div>
      </div>

      <div style="display: flex; gap: 8px;">
        <button class="btn" onclick="toggleFavorite('${kg.id}'); openDetailModal('${kg.id}')">
          ${isFav ? "❤️ 찜 완료" : "🤍 관심 찜하기"}
        </button>
        <button class="btn primary" onclick="toggleCompare('${kg.id}'); openDetailModal('${kg.id}')">
          ${inCmp ? "✓ 비교함에 담김" : "+ 비교함에 담기"}
        </button>
      </div>
    </div>

    <!-- 비용 상세 -->
    <div class="detail-section">
      <h4 class="detail-sec-title">
        <span>💸 월 학부모 실부담금 상세</span>
        <span style="color: var(--primary);">${formatWon(kg.cost.monthlyTotal)} / 월</span>
      </h4>
      <div class="kv-list">
        <div class="kv-row"><span class="kv-key">기본 수업료 (학부모 부담분)</span><span class="kv-val">${formatWon(kg.cost.tuition)}</span></div>
        <div class="kv-row"><span class="kv-key">방과후 과정비</span><span class="kv-val">${formatWon(kg.cost.afterSchoolFee)}</span></div>
        <div class="kv-row"><span class="kv-key">특성화 활동비 · 현장학습비</span><span class="kv-val">${formatWon(kg.cost.specialActivityFee)}</span></div>
        <div class="kv-row"><span class="kv-key">급식·간식비</span><span class="kv-val">${formatWon(kg.cost.mealFee)}</span></div>
      </div>
      <p style="font-size: 0.78rem; color: var(--text-sub); margin: 10px 0 0; background: var(--surface-sub); padding: 8px 10px; border-radius: 8px;">
        💡 ${escapeHtml(kg.cost.note)}
      </p>
    </div>

    <!-- 연령별 학급 및 원아 현황 -->
    <div class="detail-section">
      <h4 class="detail-sec-title">
        <span>👧 연령별 학급 · 원아 현황</span>
        <span style="font-size: 0.82rem; color: var(--text-sub);">총 ${kg.enrolledTotal} / ${kg.capacityTotal}명</span>
      </h4>
      <div class="kv-list">
        <div class="kv-row"><span class="kv-key">만 3세반 (${kg.classes.age3.count}학급)</span><span class="kv-val">현원 ${kg.classes.age3.enrolled}명 / 정원 ${kg.classes.age3.capacity}명</span></div>
        <div class="kv-row"><span class="kv-key">만 4세반 (${kg.classes.age4.count}학급)</span><span class="kv-val">현원 ${kg.classes.age4.enrolled}명 / 정원 ${kg.classes.age4.capacity}명</span></div>
        <div class="kv-row"><span class="kv-key">만 5세반 (${kg.classes.age5.count}학급)</span><span class="kv-val">현원 ${kg.classes.age5.enrolled}명 / 정원 ${kg.classes.age5.capacity}명</span></div>
        ${kg.classes.special.count > 0 ? `<div class="kv-row"><span class="kv-key">특수학급 (${kg.classes.special.count}학급)</span><span class="kv-val">현원 ${kg.classes.special.enrolled}명 / 정원 ${kg.classes.special.capacity}명</span></div>` : ""}
      </div>
    </div>

    <!-- 교직원 및 돌봄/통학 환경 -->
    <div class="detail-section">
      <h4 class="detail-sec-title"><span>👩‍🏫 교직원 안정성 & 등하원·돌봄</span></h4>
      <div class="kv-list">
        <div class="kv-row"><span class="kv-key">교사 1인당 원아 수</span><span class="kv-val">1 : ${d.ratio}명 (담임·보직 ${kg.teachers.regularTeacher}명)</span></div>
        <div class="kv-row"><span class="kv-key">4년 이상 장기근속 교사 비율</span><span class="kv-val">${d.veteranPct}% (${kg.teachers.over4yr}명 / 전체 ${kg.teachers.total}명)</span></div>
        <div class="kv-row"><span class="kv-key">기본 교육과정 시간</span><span class="kv-val">${escapeHtml(kg.operation.eduTime)}</span></div>
        <div class="kv-row"><span class="kv-key">방과후(돌봄) 운영 시간</span><span class="kv-val">${escapeHtml(kg.operation.afterSchoolTime)}</span></div>
        <div class="kv-row"><span class="kv-key">방학 중 돌봄 운영</span><span class="kv-val">${escapeHtml(kg.operation.vacationCare)}</span></div>
        <div class="kv-row"><span class="kv-key">통학버스 운행</span><span class="kv-val">${kg.operation.hasBus ? `운행 (${kg.operation.busCount}대)` : "미운행"}</span></div>
        <div class="kv-row"><span class="kv-key">급식 방식</span><span class="kv-val">${escapeHtml(kg.operation.mealType)}</span></div>
      </div>
    </div>

    <!-- 시설 및 안전 -->
    <div class="detail-section">
      <h4 class="detail-sec-title"><span>🛡️ 시설 면적 & 안전점검 현황</span></h4>
      <div class="kv-list">
        <div class="kv-row"><span class="kv-key">원아 1인당 교실 면적</span><span class="kv-val">${kg.facilitySafety.perChildAreaSqm}㎡ (총 교실 ${kg.facilitySafety.classroomAreaSqm}㎡)</span></div>
        <div class="kv-row"><span class="kv-key">실내 체육장 / 실외 놀이터</span><span class="kv-val">실내 ${kg.facilitySafety.indoorGymSqm}㎡ / 실외 ${kg.facilitySafety.outdoorPlaygroundSqm}㎡</span></div>
        <div class="kv-row"><span class="kv-key">CCTV 설치 대수</span><span class="kv-val">총 ${kg.facilitySafety.cctvTotal}대 설치</span></div>
        <div class="kv-row"><span class="kv-key">소방·가스·전기·실내공기질·놀이시설 점검</span><span class="kv-val" style="color: var(--green-text);">✓ 전 항목 적격 완료</span></div>
      </div>
      <div style="display: flex; gap: 8px; margin-top: 14px;">
        <a class="btn" href="tel:${escapeHtml(kg.phone)}" style="text-decoration: none;">📞 유치원 전화문의</a>
        <a class="btn outline-primary" href="${escapeHtml(kg.homepage)}" target="_blank" rel="noopener noreferrer" style="text-decoration: none;">🔗 유치원알리미 원문</a>
      </div>
    </div>

    ${renderCoupangCurationWidget("🎒 우리 아이 첫 유치원 등원 준비물 미리 보기")}
  `;

  backdrop.classList.add("open");
}

function closeModal() {
  document.getElementById("modal-backdrop").classList.remove("open");
}

/* ================= 찜한 목록 탭 & 가이드 탭 렌더링 ================= */
function renderFavoritesTab() {
  const container = document.getElementById("fav-card-list");
  if (!container) return;
  const favKgs = [...state.favorites].map((id) => KG_MAP.get(id)).filter(Boolean);

  if (favKgs.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div style="font-size: 2.2rem; margin-bottom: 8px;">🤍</div>
        <strong style="display: block; font-size: 1rem; color: var(--text); margin-bottom: 4px;">아직 찜한 유치원이 없어요</strong>
        <p style="font-size: 0.84rem; margin: 0 0 14px;">마음에 드는 유치원 카드 우측 상단의 하트(🤍)를 눌러 저장해 보세요.</p>
        <button class="btn primary" style="max-width: 180px; margin: 0 auto;" onclick="switchTab('explore')">유치원 둘러보기</button>
      </div>
    `;
    return;
  }

  container.innerHTML = favKgs.map(renderKgCard).join("");
}

function renderGuideTab() {
  const container = document.getElementById("guide-content");
  if (!container) return;

  const timelineHtml = `
    <div class="detail-section">
      <h3 class="detail-sec-title">🗓️ 유보통합포털(구 처음학교로) 입학 타임라인</h3>
      <div style="display: grid; gap: 10px;">
        ${ADMISSION_GUIDE_DATA.timeline
          .map(
            (t) => `
          <div style="padding: 12px; border-radius: 12px; background: ${t.active ? "var(--primary-soft)" : "var(--surface-sub)"}; border: 1px solid ${t.active ? "var(--primary)" : "transparent"};">
            <div style="display: flex; justify-content: space-between; font-size: 0.78rem; font-weight: 800; color: var(--primary); margin-bottom: 2px;">
              <span>${escapeHtml(t.step)} ${t.active ? "· [지금 집중 시기]" : ""}</span>
              <span>${escapeHtml(t.period)}</span>
            </div>
            <strong style="font-size: 0.94rem; display: block; margin-bottom: 2px;">${escapeHtml(t.title)}</strong>
            <p style="font-size: 0.82rem; color: var(--text-sub); margin: 0;">${escapeHtml(t.desc)}</p>
          </div>
        `
          )
          .join("")}
      </div>
    </div>
  `;

  const checklistsHtml = ADMISSION_GUIDE_DATA.checklists
    .map(
      (c) => `
    <div class="detail-section">
      <h3 class="detail-sec-title">${escapeHtml(c.title)}</h3>
      <div style="display: grid; gap: 8px; font-size: 0.86rem; color: var(--text);">
        ${c.items.map((line) => `<div style="padding: 8px 10px; background: var(--surface-sub); border-radius: 8px;">${escapeHtml(line)}</div>`).join("")}
      </div>
    </div>
  `
    )
    .join("");

  container.innerHTML = timelineHtml + checklistsHtml + renderCoupangCurationWidget();
}

/* ================= 하단 탭 전환 및 토스트 ================= */
function switchTab(tabName) {
  state.activeTab = tabName;
  document.querySelectorAll(".view-section").forEach((sec) => {
    sec.classList.toggle("active", sec.id === `tab-${tabName}`);
  });
  document.querySelectorAll(".bottom-tabbar .tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-tab") === tabName);
  });

  if (tabName === "explore") renderExploreList();
  if (tabName === "compare") renderCompareTab();
  if (tabName === "favorites") renderFavoritesTab();
  if (tabName === "guide") renderGuideTab();

  updateBadgesAndBars();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

let toastTimer = null;
function showToast(msg) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.remove("show");
  }, 2200);
}

// 초기 실행
document.addEventListener("DOMContentLoaded", () => {
  loadPersistedState();
  initRegionSelectors();
  syncConditionChipsUI();
  renderExploreList();
  renderCompareTab();
  renderFavoritesTab();
  renderGuideTab();
  updateBadgesAndBars();
});
