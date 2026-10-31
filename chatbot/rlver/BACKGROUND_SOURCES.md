# 배경 시드의 근거와 지금 설계 (2026-10-21)

`data/rlver/backgrounds.csv` 의 이름·성씨·나이·성별·지역·생활 상황·직업·수단이 어디서 왔는지와, 코드에 들어 있는 실제 값.
원래 336개는 [build_profile.py](../build_profile.py) 시드 → [gen_scene.py](../gen_scene.py) (GPT-6 Sol) → [backgrounds.py](backgrounds.py) 정리. 새 120개는 [gen_crisis_backgrounds.py](gen_crisis_backgrounds.py). 근거 원문 정리는 [SIMULATOR_EVIDENCE.md](../SIMULATOR_EVIDENCE.md).

구분: **근거** 통계·문헌 값 그대로 · **근거+조정** 통계를 바탕으로 바꿈 · **설계** 근거 없이 정함 (전문가 확인 대상) · **확인 필요** 2차 자료(보도·요약)로만 확인

> 링크는 SIMULATOR_EVIDENCE.md (2026-10-05) 에 적힌 것을 옮겼다. 이번에 다시 열어 확인하지는 않았다.

## 0. 한눈에

| 축 | 근거 | 구분 | 자료 |
|---|---|---|---|
| 나이·성별 | 2021 우울증 진료 인원 × 2025 생성형 AI 경험률 | 근거 (AI 경험률은 2차 자료, 50대 값은 추정) | [5] [6] |
| 성씨 | 2015 인구주택총조사 상위 20개 비율 | 근거 (상위 5개 외 확인 필요) | [7] |
| 이름 | 출생 세대별 흔한 이름을 참고해 손으로 쓴 목록 | 설계 | — |
| 지역 | 서울을 가장 크게 둔 가중치 (모델에 맡기니 대전 31%로 몰려서) | 설계 (인구 비율 근사, 출처 미기재) | — |
| 생활 상황 | 연령대별 한국 맥락을 손으로 쓴 목록 | 설계 | — |
| 직업 | 연령대별 손으로 쓴 목록 (모델에 맡기니 '작은 회사 사무직'으로 몰려서) | 설계 | — |
| 자살 수단 종류 | 2023 응급실 자살시도 방법 분포를 생각·계획 단계에 맞게 조정 | 근거+조정 | [1] [2] |
| 자해 수단 종류 | 국내 청소년 자해 연구의 방법 분포를 성인 포함으로 조정 | 근거+조정 (확인 필요) | [3] [4] |
| 새 120개·정리용 목록 | 2026-10-21 손으로 쓴 목록 | 설계 | — |

## 1. 나이·성별 (근거)

가중치 = 연령대·성별 우울증 진료 인원 [5] × 연령대 생성형 AI 경험률 [6]. 연령대 안에서는 균등. 10대는 13~19세, 70대 이상·10대 미만은 제외 (70대 이상 AI 경험률 4.9%, 사용자 결정).

| 연령대 | 나이 | 우울증 진료 남 (2021) | 여 (2021) | 생성형 AI 경험률 (2025) | → 설계 비율 | 지금 456개 |
|---|---|---|---|---|---|---|
| 10s | 13~19 | 21,157 | 36,430 | 59.7% | 8.3% | 47 |
| 20s | 20~29 | 60,112 | 117,054 | 75.3% | 32.4% | 141 |
| 30s | 30~39 | 46,473 | 93,797 | 71.1% | 24.2% | 90 |
| 40s | 40~49 | 45,898 | 84,820 | 58.4% | 18.5% | 85 |
| 50s | 50~59 | 42,206 | 87,853 | 36.4% (추정: 40·60대 중간값) | 11.5% | 53 |
| 60s | 60~69 | 43,506 | 104,533 | 14.3% | 5.1% | 34 |
| 70대 | — | — | — | 4.9% | 제외 | 6 (새 배경에서 생김) |

- 성별: 설계상 여성 66% (진료 인원이 여성 약 2.1배, AI 경험률은 성별 구분 없음). 지금 456개: 여 303 · 남 153
- 확인 필요: 50대 AI 경험률 36.4% 는 보도에 없어 40대·60대 중간값. 보고서 원문으로 바꿔야 한다.
- 쓰지 않은 자료: 비대면진료 시범사업 연령 분포 (감기·만성질환 재진이 대부분이라 성격이 다름).

## 2. 성씨 (근거 [7])

| Kim | Lee | Park | Choi | Jung | Kang | Cho | Yoon | Jang | Lim | Han | Oh | Seo | Shin | Kwon | Hwang | Ahn | Song | Jeon | Hong |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 21.5 | 14.7 | 8.4 | 4.7 | 4.3 | 2.4 | 2.1 | 2.1 | 2.0 | 1.7 | 1.5 | 1.5 | 1.4 | 1.4 | 1.4 | 1.4 | 1.4 | 1.3 | 1.1 | 1.1 |

단위 %. 상위 5개 외 값은 확인 필요.

## 3. 이름 (설계)

원래 시드 목록 (`build_profile.GIVEN`, 세대 = 나이 35 미만 / 35~54 / 55 이상). 출생연도별 흔한 이름을 참고해 손으로 썼다.

| 세대·성별 | 이름 (개수) |
|---|---|
| young · male | Min-jun, Seo-jun, Do-yun, Ha-jun, Ji-ho, Jun-woo, Hyun-woo, Ji-hoon, Geon-woo, Woo-jin, Seung-min, Yu-jun, Jae-won, Tae-yang, Si-woo, Dong-hyun (16) |
| young · female | Seo-yeon, Ji-woo, Seo-yun, Ha-eun, Min-seo, Ji-yoon, Chae-won, Su-ah, Ye-eun, Da-eun, Yu-na, So-yul, Ji-min, Su-bin, Ga-eun, Na-yeon (16) |
| middle · male | Jun-ho, Sung-min, Dong-hoon, Jae-hyun, Sang-woo, Hyun-soo, Jin-woo, Jung-hoon, Ki-hyun, Seung-hyun, Min-soo, Tae-hoon, Sung-ho, Jae-min (14) |
| middle · female | Ji-young, Eun-jung, Hye-jin, Mi-young, Sun-young, Ji-eun, Eun-young, Su-jin, Hyun-jung, Yoon-hee, Mi-ra, Jung-eun, Hee-jung, Soo-yeon (14) |
| older · male | Young-ho, Young-soo, Sang-chul, Jong-hoon, Kwang-soo, Byung-chul, Man-sik, Chang-ho, Dong-su, Myung-ho, Jae-sik, Yong-hwan (12) |
| older · female | Mi-kyung, Young-hee, Kyung-ja, Sook-ja, Eun-sook, Myung-hee, Jung-sook, Soon-ja, Mi-sook, Hyun-sook, Kyung-hee, Young-ja (12) |

- 목록이 세대·성별마다 12~16개뿐이라 젊은 여성(약 100명)에서 Seo-yeon 15명처럼 몰렸다.
- 2026-10-21 정리: 같은 이름은 3번까지, 넘는 189명을 아래 목록으로 바꿨다 (세대 = 30 미만 / 30~54 / 55 이상). 이것도 설계.

| 세대·성별 | 정리에 쓴 이름 목록 |
|---|---|
| young · female | Ha-young, Seo-young, Ji-yeon, Ye-ji, Ah-young, Soo-min, Min-a, Hee-won, Seo-jin, Bo-ra, Han-na, Dan-bi, Sae-rom, Ha-jin, Do-yeon, Yun-ah, Ji-won, Seo-won, Ha-na, Eun-bi, Su-yeon, Ye-rim, Ga-hyun, Yoo-jin, Chae-yeon, Seo-ah, Ha-eun, Ye-jin, Da-in, Yu-jin, Si-eun, Chae-rin, Ga-on, Ha-rin, So-eun, Ye-seo, Ha-yoon, Ji-an, Yoon-seo, Seo-hyun, Da-hyun, Eun-chae, Ye-na, Ji-yu, Su-hyun, Ga-young, Hye-rin, Min-ji, Yeon-woo, Bo-min, Seo-rin, Ji-ah, Na-eun, Ye-won, Da-bin, Hyo-jin, Se-eun, A-rin |
| young · male | Min-gyu, Ji-hun, Tae-hyun, Jung-hoon, Ye-chan, Gyu-min, Sang-hyun, Young-woo, Hyeon-seo, Dong-ha, Do-yoon, Ye-jun, Si-woo, Jun-seo, Yu-chan, Ji-ho, Seung-hyun, Tae-yoon, Gun-woo, Eun-woo, Ji-hwan, Hyun-jun, Woo-jin, Seon-woo, Jun-young, Min-hyuk, Do-hyun, Jae-min, Sung-min, Ji-sung, Han-gyeol, Yoon-ho, Joo-ho, Tae-min, Kyung-min, Chan-young, Min-sung, Jin-hyuk, Si-hoo, Ha-ram |
| mid · female | Hye-kyung, Mi-hyun, Eun-kyung, Hyo-jung, Mi-ran, Eun-sun, Kyung-mi, Ae-kyung, Sung-hee, Yoo-kyung, Hee-sun, Jin-sook, Mi-hee, Hyun-mi, Sun-mi, Young-mi, Eun-joo, Hye-sun, Jeong-a, Bo-kyung, Yeon-joo, Su-kyung, Hye-won, Ji-hye, Mi-jin, Su-jin, Hyun-ah, Jin-hee, Bo-young, Seon-mi, Yeon-hee, Eun-ha, Min-jung, Hye-jin, Jung-hwa, Soo-kyung, Mi-sun, Kyung-hee, Sun-hee, Ji-sun, Hye-young, Eun-mi, Yoon-jung, So-young, Jung-mi, Hae-jin, Myung-hee, In-hye, Ji-eun, Seung-hee, Hyun-joo, Mi-kyung |
| mid · male | Dong-hoon, Sung-jin, Hyun-seok, Jae-woong, Ki-hoon, Young-soo, Tae-ho, Chul-min, Jin-ho, Seung-woo, Sung-hoon, Hyun-woo, Jae-hyuk, Sang-woo, Ki-tae, Joon-ho, Young-jae, Won-jae, Tae-gyu, Jin-woo, Seung-ho, Jong-hyun, Byung-hoon, Dong-wook, Jae-sung, Hyung-jun, Kwang-ho, Sang-hoon, Dae-ho, Min-seok, In-ho, Jung-woo, Seok-jin, Ho-jin, Yong-ho, Chang-min, Hee-chul, Young-min, Jun-hyuk |
| older · female | Ok-soon, Mal-sook, Geum-ja, Kyung-ja, Young-hee, Soon-ja, Myung-ok, Jeong-suk, Mi-ok, Sun-ok, Bok-hee, Chun-ja, Young-sook, Soon-hee, Jung-ja, Ok-ja, Kum-sun, Bok-soon, Yang-ja, Hwa-ja, Mi-ja, Jeom-rye, Sook-hee, Kyung-ok, Gil-ja, Yeon-ok, Soon-ok, Mal-soon, In-sook, Bong-sook |
| older · male | Byung-chul, Chul-soo, Man-sik, Deok-man, Young-gil, Hak-soo, Jong-pil, Chang-ho, Dae-sung, Myung-soo, Bong-gu, Yong-bae, Gwang-soo, Sang-chul, Young-ho, Il-hwan, Jong-dae, Soo-man, Kil-soo, Ki-sik, Tae-sik, Pyung-ho, Jae-gil, Moon-soo, Dong-chun, Sung-man, Ho-sik, Kyu-sik, Byung-soo, Nam-il |

## 4. 지역 (설계)

모델에 맡기면 대전·인천·수원으로 몰려서 (v3 중간 결과 31% 대전) 시드로 넣었다. 서울을 가장 크게 둔 건 사용자 결정. 값은 인구 비율에 가깝게 잡았지만 출처는 문서에 없다.

| 지역 | 가중치 | 도시 (도 단위는 하나를 고름) |
|---|---|---|
| Seoul | 30 | — |
| Gyeonggi | 24 | Suwon, Seongnam, Goyang, Yongin, Bucheon, Ansan, Hwaseong, Namyangju, Uijeongbu, Pyeongtaek, Paju, Gimpo |
| Busan | 7 | — |
| Incheon | 6 | — |
| Daegu | 5 | — |
| Gwangju | 3 | — |
| Daejeon | 3 | — |
| Ulsan | 2 | — |
| Gyeongnam | 4 | Changwon, Gimhae, Jinju |
| Gyeongbuk | 3 | Pohang, Gumi, Gyeongju |
| Chungnam | 3 | Cheonan, Asan |
| Jeonbuk | 2 | Jeonju, Iksan |
| Jeonnam | 2 | Suncheon, Yeosu, Mokpo |
| Chungbuk | 2 | Cheongju, Chungju |
| Gangwon | 2 | Wonju, Chuncheon, Gangneung |
| Jeju | 2 | Jeju City |

- 주의: 학습용 처음 258개는 지역 시드 없이 생성 (대전 쏠림 그대로, 사용자 결정 2026-10-05). 정본에는 지역 열이 없고 배경 글에만 나온다.
- 지금 456개 배경 글에 처음 나오는 도시 (대충): 기타·없음 144, Seoul 74, Incheon 53, Daejeon 52, Suwon 33, Busan 23, Daegu 20, Gwangju 15. 대전이 인천과 비슷하게 많다.

## 5. 생활 상황 (설계) — 배경 사건의 주 소재

`build_profile.LIFE`. 연령대별로 손으로 쓴 한국 맥락 목록, 균등하게 하나. 괄호는 그 성별만.

| 연령대 | 생활 상황 |
|---|---|
| 10s | college entrance exam (suneung) pressure, class ranking pressure, bullying, family conflict, left out of friend group, parents' expectations |
| 20s | job hunting, civil service exam prep, overwork at first job, breakup, student loans, living alone in a small studio, military service (male) |
| 30s | workplace overwork, marriage pressure from family, childcare and career, housing costs, infertility (female), layoff |
| 40s | workplace pressure, children's education costs, marital conflict, caring for aging parents, small business struggles, mortgage debt |
| 50s | early retirement, small business failure, empty nest, health decline, caring for aging parents, divorce |
| 60s | retirement and loss of role, chronic illness, financial insecurity, loss of a spouse, distance from adult children |

## 6. 직업 (설계)

`build_profile.OCCUPATION`. 파일럿에서 직업이 '작은 회사 사무직'으로 몰려서 넣은 연령대별 목록. 성별 제한은 군인 하나뿐이었다. 이 값을 페르소나 단계에서 LLM 이 구체화했다 (직장·역할).

| 연령대 | 직업 |
|---|---|
| 10s | 13~15 middle school student · 16~18 high school student / vocational high school student · 19 university freshman / student retaking the college entrance exam / part-time worker (`teen_occupation`) |
| 20s | university student, graduate student, office worker at a large company, office worker at a small firm, nurse, software developer, cafe or convenience-store part-timer, delivery rider, kindergarten teacher, call center agent, factory worker, hair salon assistant, freelance designer, startup employee, conscript soldier (male) |
| 30s | office worker at a large company, office worker at a small firm, nurse, school teacher, software engineer, sales representative, cafe owner, freelancer, stay-at-home parent, contract worker, civil servant, researcher, delivery driver, physical therapist, insurance planner |
| 40s | middle manager, small business owner, school teacher, nurse, civil servant, taxi driver, construction site manager, real-estate agent, stay-at-home parent, restaurant owner, factory team leader, insurance planner, academy (hagwon) instructor |
| 50s | department head, restaurant owner, taxi driver, security guard, care worker, cleaner, civil servant, farmer, real-estate agent, small manufacturer owner, school administrative staff |
| 60s | retired, apartment security guard, care worker, farmer, part-time cleaner, small shop owner, taxi driver, senior public job program worker |

생활 상황이 신분을 정하면 직업을 덮어쓴다 (`LIFE_OCCUPATION`):

| 생활 상황 | → 직업 |
|---|---|
| job hunting | job seeker |
| civil service exam prep | civil service exam candidate |
| military service | conscript soldier |
| early retirement | recently took early retirement |
| retirement and loss of role | retired |
| layoff | recently laid off |
| job loss | recently lost their job |
| small business struggles | small business owner |
| small business failure | owner of a failing small business |

- 쏠림의 원인 (2026-10-21 확인): 20대 생활 상황 6~7개 중 하나가 'civil service exam prep' 이고 20대가 32% 라 9급 공시생 32명. 직업에 성별 제한이 없고 여성이 2배 넘게 뽑혀 여성 택시 기사 6/7·배달 13/15·건설 소장 4/6·경비원 4/6.
- 2026-10-21 정리 (69명): 아래 목록에서 나이·성별에 맞게 골라 직업 칸·직장 문장만 고쳤다. 이것도 설계.

| 정리 대상 (남긴 수) | |
|---|---|
| 공시생 | 6명 남김 |
| 포장재 사무 | 2명 남김 |
| 여성 배달 | 2명 남김 |
| 여성 택시 | 1명 남김 |
| 여성 건설 소장 | 1명 남김 |
| 여성 경비 | 1명 남김 |
| 보험설계사 | 4명 남김 |
| 공인중개사 | 4명 남김 |
| 청소원 | 4명 남김 |

| 세대·성별 | 바꿀 때 쓴 직업 목록 |
|---|---|
| young · female | student retaking the college entrance exam, candidate preparing for the teacher certification exam, student preparing to transfer universities, CPA exam candidate, social welfare major at a university, new hire at a bank branch, junior marketer at a cosmetics brand, webtoon studio assistant, assistant teacher at a daycare center, pharmacy assistant, content editor at a small startup, nail artist, junior writer at a broadcasting production company, airline ground staff, travel agency staff, fitness trainer, baker at a neighborhood bakery, veterinary technician at an animal hospital, editorial assistant at a publishing house, event planner at a small agency, law school student, architecture student, assistant merchandiser at a fashion company, nurse aide at a Korean medicine clinic, staff at a tax accountant's office, dental technician, kids-café staff, photo studio assistant, music therapist trainee, graduate student in psychology |
| young · male | student retaking the college entrance exam, candidate preparing for the police officer exam, candidate preparing for the firefighter exam, CPA exam candidate, new hire at a mid-size construction company's office, line cook at a Korean restaurant, sound engineer assistant, junior web developer, electrician's apprentice, fitness trainer, graduate student in chemistry, student preparing to transfer universities, baker at a franchise bakery, junior salesperson at a car dealership, logistics center office staff, photographer's assistant, interior design trainee, esports coach assistant, vocational school welding student, assistant chef at a hotel buffet |
| mid · female | daycare center director, pharmacist at a neighborhood pharmacy, office manager at a tax accountant's office, consultation manager at a dermatology clinic, owner of a side-dish shop, owner of a small craft workshop, owner of a neighborhood hair salon, assistant manager at a bank branch, hospital admissions office staff, wedding planner, social worker at a community welfare center, paralegal at a law office, book editor at a publishing house, owner of a small neighborhood bookstore, tour guide for foreign visitors, school administrative staff, accounting clerk at a mid-size company, home-shopping call center team leader, dietitian at a hospital, pilates studio owner |
| mid · male | electrical maintenance engineer, interior construction technician, excavator operator, car salesman, cargo truck driver, police officer at a local precinct, restaurant cook, logistics center manager, wedding photographer, welder at a shipyard subcontractor, HVAC repair technician, fish auction broker, middle manager at a mid-size company, IT support engineer, pharmaceutical company researcher, owner of a small print shop |
| older · female | owner of a side-dish stall in a traditional market, kitchen assistant at a restaurant, care worker at a nursing home, neighborhood tong-jang (local representative), owner of a clothing alterations shop, owner of a small kimbap shop, postpartum caregiver, housekeeper for several households, farmer growing peppers and sesame, retired nurse, school crossing-guard in a senior jobs program, owner of a small fabric shop |
| older · male | cargo truck driver, village bus driver, parking lot attendant, farmer growing apples, retired office worker, apartment management office chief, carpenter, fisherman, scrap metal dealer, facility maintenance worker at a school, retired high school teacher, owner of a small motorcycle repair shop |

## 7. 수단 종류 (근거+조정)

risk_fact 에 쓸 수단 **종류**만 시드로 정한다 (문장은 LLM, 약 이름·용량·방법 설명은 금지). 종류가 필요한 이유: 대응 지침의 '수단 멀리 두기'·Stanley-Brown 안전계획의 수단 제한 단계.

### 자살 관련 (방법·수단 접근·계획·의도·시도·준비)

| 수단 | 비율 | 근거 |
|---|---|---|
| medication at home | 50% | 응급실 내원 자살시도 방법 음독 53.1% [1], 중독 시도 주요 물질은 치료약물 [2] |
| sharp object | 15% | 같은 자료 둔기/예기 18.4% [1] |
| high place | 10% | 응급실 자료에선 적게 잡혀 올림 (아래) |
| hanging | 8% | 같음 |
| gas in a car or closed room | 7% | 같은 자료 가스 5.3% [1] |
| pesticide or chemicals | 5% | 같은 자료 농약 5.3% [1]. 50세 이상만 (설계, 농촌 고령층) |
| not decided yet | 5% | 설계. 방법만 생각하고 정하지 않은 경우 (수단 접근·계획·의도에선 제외) |

- 조정 이유: [1] 은 살아서 응급실에 온 시도자 기준이라 치명도 높은 수단(높은 곳·목맴)이 생각·계획 단계보다 적게 잡힌다. 우리 사용자는 생각·계획 단계가 많아 이 둘을 올리고 약을 조금 내렸다 (사용자 확인 2026-10-05).
- 같은 자료 참고값: 시도 장소 자택 58.8%, 음주 상태 31.2%, 현재 정신과 치료 중 41.9%, 여성 64.8%.

### 자해 (자해 행동, 자살 의도가 있는 자해)

| 수단 | 비율 | 근거 |
|---|---|---|
| sharp object | 70% | 국내 청소년 연구에서 자해의 약 80%가 베기·찌르기, 중고생 1순위 방법은 긋기 [3][4] — 확인 필요 (검색 요약으로 봄). 성인 포함이라 낮춤 |
| hitting or burning | 20% | 같은 연구들에서 다음으로 많은 유형 [3][4] |
| medication overdose | 10% | 설계. 자살 의도가 불분명한 과다복용 |

## 8. 새 배경 120개에 쓴 목록 (설계, 2026-10-21)

[gen_crisis_backgrounds.py](gen_crisis_backgrounds.py). 근거 없이 손으로 쓴 목록이다.

**고위험 60 (유서·물건 정리·물질)**: 나이 19~72 (네 구간 중 하나에서 균등), 성별 반반 확률, 도시·삶의 영역은 아래에서 균등, 세부 유형은 번호마다 돌아가며.

| 목록 | 값 |
|---|---|
| 도시 | Seoul, Busan, Incheon, Daegu, Daejeon, Gwangju, Ulsan, Suwon, Cheongju, Jeonju, Changwon, Gangneung, Jeju, Pohang, Chuncheon, Mokpo, Andong, Gimhae, Yeosu, Wonju |
| 삶의 영역 | jeonse or rent deposit, caring for a sick parent, a failed small business, military service or its aftermath, a university entrance or civil-service exam, divorce or separation, a chronic illness or injury, debt or a loan, job loss or forced early retirement, bereavement, workplace bullying, raising a child alone, farming or fishing work in a rural area, moving to a new city alone, an unpaid wage dispute, fertility treatment, a sibling or family feud, loneliness after retirement, a gig or delivery job, a music, art, or sports career that stalled |
| 세부 유형: suicide_note | a handwritten letter on paper / a phone memo / an unsent text or KakaoTalk message / an email saved as a draft / a letter to one specific person (a child, parent, partner, or friend) |
| 세부 유형: put_affairs_in_order | giving away valued possessions / arranging who will look after a pet or child / sorting out money, insurance, a will, or bank accounts / deleting accounts, photos, or messages / quiet goodbyes (visiting or calling people to say thank you) |
| 세부 유형: substance_use_disorder | alcohol / alcohol / sleeping pills or sedatives once prescribed / a stimulant or another illegal drug / alcohol together with sleeping pills |

**가벼운 우울 60 (mild)**: 주제 6개 × 10, 나이는 주제 범위 안에서 균등, 성별 반반, 이름은 세대별 목록, 직업은 나이에 맞는 후보 3개 중 모델이 성별까지 보고 고름, 끝 감정 8개 순환.

| 주제 | 나이 | 세부 상황 |
|---|---|---|
| a breakup or relationship letdown | 19~62 | being ghosted after a few dates / a breakup they started but now doubt / a long-distance relationship fading / a partner or spouse forgetting something that mattered to them / seeing an ex move on quickly / a dating-app match that went nowhere / a spouse who keeps brushing off plans together / a quiet argument with a partner that is still unresolved |
| irritation at someone | 17~72 | a roommate or family member who never cleans up / a coworker taking credit / a rude customer / upstairs neighbor noise / a sibling who keeps borrowing things / in-laws or relatives commenting on their life / a group-project member who did nothing / a landlord or building office ignoring a small repair |
| a mistake they made | 17~72 | sending a message to the wrong group chat / a small calculation or ordering error at work / forgetting a family member's birthday / missing an appointment they had promised to keep / breaking something borrowed / saying something awkward in front of people / losing a wallet or phone for a day / a typo in something many people saw |
| studying or exams | 16~29 | a mock exam score that dropped / a presentation that went badly / harsh feedback from a professor or advisor / failing a certification or license test by a few points / falling behind on a group assignment / a scholarship they did not get / a driving-license test they failed / a TOEIC or language score below their goal |
| a cold, flu, or minor illness | 17~72 | a cold during an important week / a stomach bug that ruined a trip / a flu that made them miss a family event / a lingering cough that keeps them from their hobby / a sprained ankle from a small fall / a migraine that cost them a day off |
| a problem with a friend | 17~72 | being left out of a gathering / an argument over money or a small loan / a friend who always cancels / a friend drifting away after marriage or a move / a hurtful comment in a group chat / not being invited to a friend's wedding / a friend who only talks about themselves / a friend who shared something they told in confidence |

| 직업 (자연스러운 나이) |
|---|
| vocational high school senior (17~19), first-year nursing student (19~23), convenience-store night clerk (19~30), barista at a franchise café (19~32), conscript soldier on weekend leave (19~23), trainee hairdresser (19~27), university dance major (18~24), part-time delivery rider (20~45), intern at a small game studio (22~28), art-school applicant at a drawing hagwon (18~21), junior bank teller (23~30), pet groomer (21~40), wedding-hall server (19~28), theater stagehand (21~35), university student in an engineering major (19~26), graduate student in a biology lab (24~32), elementary school teacher (24~60), subway train driver (28~58), dental hygienist (22~45), freelance translator (26~55), chicken restaurant owner (35~62), logistics center shift supervisor (30~55), pharmaceutical sales rep (26~45), apartment complex management office staff (30~62), kindergarten bus driver (40~65), UX designer at a startup (25~40), home-shopping show host (26~45), forklift operator (25~60), hotel front-desk staff (22~40), yoga instructor (24~50), electrician (25~62), taxi driver (35~72), public health center nurse (25~58), car mechanic (22~60), office worker at a mid-size company (25~50), civil servant at a district office (26~58), retired postal worker (60~72), rice farmer (45~72), public bathhouse owner (50~72), church choir conductor (40~70), apartment security guard (58~72), tailor (45~72), school cafeteria cook (40~65), fishing-boat captain (40~70), senior welfare center volunteer (60~72), small hardware-store owner (40~70), retired middle-school principal (62~72), traditional market rice-cake seller (45~72) |

| 끝 감정 |
|---|
| mostly irritated and restless, unable to settle into anything this evening / flat and unmotivated, skipping something they usually enjoy / lonely, scrolling their phone without answering anyone / ashamed and quiet, avoiding the people involved / tired and a bit tearful, going to bed earlier than usual / deflated, with work or study for tomorrow left undone / grumpy and short with family or roommates over small things / low and restless, sleeping badly the last night or two |

이름 목록 (`gen_crisis_backgrounds.GIVEN`): female·young: Seo-ah, Ha-eun, Ji-woo, Ye-jin, Da-in, Yu-jin, Si-eun, Chae-rin, Ga-on, Ha-rin, So-eun, Ye-seo; female·mid: Hye-won, Eun-jung, Ji-hye, Mi-jin, Su-jin, Hyun-ah, Jin-hee, Bo-young, Seon-mi, Yeon-hee, Eun-ha, Min-jung; female·older: Ok-soon, Mal-sook, Geum-ja, Kyung-ja, Young-hee, Soon-ja, Myung-ok, Jeong-suk, Mi-ok, Sun-ok, Bok-hee, Chun-ja; male·young: Do-yoon, Ye-jun, Si-woo, Jun-seo, Yu-chan, Ji-ho, Seung-hyun, Tae-yoon, Gun-woo, Min-jun, Eun-woo, Ha-jun; male·mid: Sung-hoon, Hyun-woo, Dong-hyun, Jae-hyuk, Sang-woo, Ki-tae, Joon-ho, Young-jae, Won-jae, Tae-gyu, Jin-woo, Seung-ho; male·older: Byung-chul, Chul-soo, Man-sik, Deok-man, Young-gil, Hak-soo, Jong-pil, Chang-ho, Dae-sung, Myung-soo, Bong-gu, Yong-bae

## 9. 참고 자료

- [1] 보건복지부 응급실 기반 자살시도자 사후관리사업 2023 통계 (85개 병원, 30,665명) — 보도 — https://www.medifonews.com/news/article.html?no=189368
- [2] 응급실 내원 자해·자살시도 보도 (중독 시도의 치료약물 비중), 경향신문 2025-02 — https://www.khan.co.kr/article/202502132043015
- [3] 비자살적 자해 국내 연구동향 2000~2019, 한국청소년연구 (NYPI) — https://www.nypi.re.kr/repository/bitstream/2022.oak/2273/2/%EB%B9%84%EC%9E%90%EC%82%B4%EC%A0%81%20%EC%9E%90%ED%95%B4(Non-Suicidal%20Self-Injury%EF%BC%9ANSSI)%EC%97%90%20%EB%8C%80%ED%95%9C%20%EA%B5%AD%EB%82%B4%EC%97%B0%EA%B5%AC%EB%8F%99%ED%96%A5%EF%BC%9A2000%EB%85%84%EB%B6%80%ED%84%B0%202019%EB%85%84%EA%B9%8C%EC%A7%80.pdf
- [4] 청소년 자해행동: 여중생의 자살적 자해와 비자살적 자해 (KCI) — https://www.kci.go.kr/kciportal/landing/article.kci?arti_id=ART002167043
- [5] 보험연구원(KIRI), 최근 5년(2017~2021년) 우울증과 불안장애 진료현황 분석 (심평원 자료) 표4 — https://kiri.or.kr/PDF/weeklytrend/20220704/trend20220704_1.pdf
- [6] 과기정통부 2025 인터넷이용실태조사 보도 (생성형 AI 경험률) — https://v.daum.net/v/20260331120317263
- [7] 통계청 2015 인구주택총조사 성씨·본관 집계 (링크 없음, KOSIS 에서 찾아야 함)
- 성격 보정 등 나머지 문헌 (Roberts 2006, Costa 2001, Kotov 2010, Noftle & Shaver 2006) 은 배경 칸에 직접 들어가지 않아 SIMULATOR_EVIDENCE.md 참고 자료 목록에만 있다.

## 10. 확인 필요 · 바꿀 만한 것

- 50대 생성형 AI 경험률 (추정값) → 과기정통부 보고서 원문
- 성씨 상위 5개 외 비율 → KOSIS 2015 인구주택총조사 원표
- 자해 수단 비율 → [3][4] 원문 확인 (지금은 검색 요약)
- 지역 가중치 출처 없음 → 주민등록인구 시도별 비율로 바꿀 수 있음
- 직업·생활 상황·이름은 모두 설계 → 통계청 지역별고용조사(연령·성별 직업 분포), 출생연도별 이름 통계로 바꿀 수 있음
