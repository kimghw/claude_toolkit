# 선박 전기설비 로드맵
- 최신 선박 적용 신기술 분석
- IACS 선급 지침 분석을 통한 갭 분석
- 기준 자료: [선박_전기설비_신기술_종합조사보고서.md](선박_전기설비_신기술_종합조사보고서.md) (2026-05-08, Multi-Agent 조사)


## 용어 정리 (Glossary)

### 전력변환·배전·추진

| 약어 | 풀네임 | 의미 |
|---|---|---|
| MVDC | Medium Voltage Direct Current | 중압 직류, 선박 IEEE 1709-2018 정의 **1~35 kV** |
| LVDC / HVDC | Low / High Voltage DC | 선박(IEC 60092): LV ≤ 1 kV / HV > 1 kV. 육상송전 HVDC는 통상 ≥100 kV (CIGRE) — 컨텍스트 주의 |
| IFEP | Integrated Full Electric Propulsion | 통합 전기추진 (발전 ↔ 추진 공유 버스) |
| PMSM | Permanent Magnet Synchronous Motor | 영구자석 동기전동기 |
| HTS | High Temperature Superconductor | 고온 초전도 (대용량·경량 모터) |
| WBG | Wide Bandgap Semiconductor | 광대역 갭 전력반도체 (SiC·GaN) |
| SiC | Silicon Carbide | 탄화규소 전력반도체 (고전압·고온) |
| GaN | Gallium Nitride | 질화갈륨 전력반도체 (고주파·저손실) |
| SST | Solid State Transformer | 반도체 변압기 |
| MOSFET | Metal-Oxide-Semiconductor Field-Effect Transistor | 전력 스위칭 소자 |
| HEMT | High Electron Mobility Transistor | 고전자이동도 트랜지스터 (GaN 계열) |
| DCCB | DC Circuit Breaker | DC 차단기 (Hybrid / Solid State / Mechanical) |
| SSCB | Solid State Circuit Breaker | 반도체식 차단기 |
| AFE | Active Front End | 능동 정류기 (회생·역률보정) |
| VFD | Variable Frequency Drive | 가변주파수 드라이브 |
| AVR | Automatic Voltage Regulator | 자동 전압조정기 |
| OPS | Onshore Power Supply | 육상전원 공급 (정박 중 항만 전력 사용) |
| HVSC | High Voltage Shore Connection | 고압 육상전원 접속 (AC > 1 kV, IEC/IEEE 80005-1:2019) |
| LVSC | Low Voltage Shore Connection | 저압 육상전원 접속 (≤1 kV 또는 ≤1 MVA, IEC/IEEE 80005-3:2025) |
| AMP | Alternative Maritime Power | 육상전원 (미국식 동의어, Port of LA 등록상표) |
| WPT | Wireless Power Transfer | 무선 전력 전송 |

### 청정 에너지원·저장

| 약어 | 풀네임 | 의미 |
|---|---|---|
| ESS | Energy Storage System | 에너지 저장 시스템 |
| BMS | Battery Management System | 배터리 관리 시스템 |
| TRP / TPP | Thermal Runaway Propagation (Prevention) | 열폭주 전파(방지) — 셀→모듈→팩. DNV-RU-SHIP Pt.6 Ch.2 §4.2.2 (※ 종전 "PPR" 표기는 비표준 약어) |
| LFP | Lithium Iron Phosphate (LiFePO₄) | 리튬인산철 배터리 (안전·장수명) |
| NMC | Lithium Nickel Manganese Cobalt Oxide | 니켈망간코발트 산화물 배터리 (NCM은 국내·중국식 동의어, NMC가 국제 주류) |
| LTO | Lithium Titanate (Li₄Ti₅O₁₂) | 리튬티탄산염 음극 (고속충방전·장수명) |
| SSB / ASSB | (All-)Solid State Battery | (전)고체 배터리 |
| SOC / SOH / SOP | State of Charge / Health / Power | 충전·건강·출력 상태 (IEC 61960) |
| SOFC | Solid Oxide Fuel Cell | 고체산화물 연료전지 (고온·고효율) |
| PEMFC | Proton Exchange Membrane Fuel Cell | 양성자 교환막 연료전지 (저온·고속응답) |
| MCFC | Molten Carbonate Fuel Cell | 용융탄산염 연료전지 |
| BOP | Balance of Plant | 연료전지 보조설비 (압축기·송풍기·humidifier 등) |
| DF | Dual-Fuel | 이중연료 (가스+디젤, IMO IGF Code) |
| LH₂ | Liquefied Hydrogen | 액화수소 (IMO MSC.420(97) 공식 표기) |
| NH₃ | Ammonia | 암모니아 (무탄소 연료·수소 캐리어) |
| PV | Photovoltaic | 태양광 |

### 전력품질·계통

| 약어 | 풀네임 | 의미 |
|---|---|---|
| PQ / PQI | Power Quality / Power Quality Index | 전력품질 / 전력품질 지표 |
| THD | Total Harmonic Distortion | 총 고조파 왜형률 (IEEE 519, IEC 61000-4-7) |
| VUF | Voltage Unbalance Factor | 전압 불평형률 (IEC 61000-3-13) |
| PCC | Point of Common Coupling | 공통접속점 (IEEE 519, IEC 61000-3-6) |
| dV/dt, dI/dt | Rate of Change of Voltage / Current | 전압·전류 변화율 |
| ROCOF | Rate of Change of Frequency | 주파수 변화율 (IEC 60255-181) |
| ROCOC | Rate of Change of Current | 전류 변화율 (DC 보호; ※ IEC/IEEE 정식 약어 아님, MVDC 학술 표기) |
| VSG | Virtual Synchronous Generator | 가상 동기발전기 (관성 에뮬레이션) |
| PCS | Power Conversion System | (ESS) 전력변환장치 (IEC 62933) |
| CT / VT (PT) | Current Transformer / Voltage (Potential) Transformer | 변류기 / 계기용 변압기 (VT: IEC 61869, PT: IEEE C57.13 북미 표기) |
| IR | Infrared (Thermography) | 적외선 열화상 |
| PD | Partial Discharge | 부분방전 (IEC 60270, IEC TS 62478) |
| DGA | Dissolved Gas Analysis | 변압기 절연유 용존가스 분석 (IEC 60599, IEEE C57.104) |
| UHF / TEV / HFCT | Ultra High Frequency / Transient Earth Voltage / High Frequency Current Transformer | PD 검출 방식 (IEC TS 62478) |

### 디지털화·AI·자동화

| 약어 | 풀네임 | 의미 |
|---|---|---|
| IAS | Integrated Automation System | 통합 자동화 시스템 |
| PMS | Power Management System | 전력관리 시스템 (선박 발전·부하 분담) |
| EMS | Energy Management System | 에너지 관리 시스템 (ISO 50001 호환) |
| SCADA | Supervisory Control And Data Acquisition | 감시제어·데이터 취득 |
| IED | Intelligent Electronic Device | 지능형 전자장치 (보호계전기 등, IEC 61850) |
| TSN | Time-Sensitive Networking | 시간 결정형 이더넷 (IEEE 802.1) |
| OPC UA | OPC Unified Architecture | 산업용 통신 표준 (IEC 62541; OPC = 고유명, 약어 아님) |
| MQTT | (구) Message Queuing Telemetry Transport | OASIS 표준 경량 메시징 (v3.1.1 이후 풀네임 폐기, MQTT는 고유 명칭) |
| DT | Digital Twin | 디지털 트윈 (ISO 23247, DNV-RP-A204) |
| Digital Thread | Digital Thread | 디지털 스레드 — 자산 생애주기(설계·제조·운영·정비·폐기) 데이터 연결선 (NIST AMS 100-24, DoD DT/DTh) |
| FMI / FMU | Functional Mock-up Interface / Unit | 다툴 모델 교환 표준 (Modelica Association) |
| HIL / PHIL | Hardware / Power Hardware In the Loop | 실시간 시뮬레이션 시험 |
| ROM | Reduced Order Model | 차수축소 모델 (실시간 DT용) |
| EAM | Enterprise Asset Management | 전사 자산관리 (ISO 55000) |
| APM | Asset Performance Management | 자산 성능관리 |
| CMMS | Computerized Maintenance Management System | 전산 정비관리 시스템 (EN 13306) |
| RUL | Remaining Useful Life | 잔여 수명 (ISO 13381-1) |
| CBM / PdM | Condition-Based Maintenance / Predictive Maintenance | 상태기반 / 예지 정비 (ISO 17359) |
| MTBF / MTTR | Mean Time Between Failures / Mean Time To Repair | 평균 고장간격 / 수리시간 (IEC 60050-192) |
| RBI | Risk-Based Inspection | 위험기반 검사 (API 580, DNV/LR/ABS Hull GN) |
| LLM / RAG | Large Language Model / Retrieval-Augmented Generation | 거대 언어모델 / 검색증강 생성 |
| LSTM / DRL | Long Short-Term Memory / Deep Reinforcement Learning | 시계열 RNN / 심층 강화학습 |
| AE | Autoencoder | 오토인코더 (이상탐지) |
| FFT / STFT / DWT | Fast / Short-Time / Discrete Wavelet Transform | 주파수 분석 기법 |

### 자율운항·검사·승인

| 약어 | 풀네임 | 의미 |
|---|---|---|
| MASS | Maritime Autonomous Surface Ship | 자율운항 선박 (IMO MASS Code 2026.5 비강제판) |
| UMS (E0/ACCU/AUT-UMS) | Unattended Machinery Space | 무인 기관실 노테이션 — DNV **E0**, ABS **ACCU/ACC**, LR **UMS**, BV **AUT-UMS** (선급별 표기 상이) |
| AROS | Autonomous and Remotely Operated Ships | DNV 자율운항 노테이션 (2025.1 발효, navigation·engineering·operational·safety 4기능 × 4 자율도) |
| ROC | Remote Operations Centre | 육상 원격운항 센터 (DNV 공식 표기) |
| VDES | VHF Data Exchange System | VHF 데이터 교환 시스템 (ITU-R M.2092) |
| AR / VR / MR / XR | Augmented / Virtual / Mixed / eXtended Reality | 증강·가상·혼합·확장 현실 |
| LiDAR / SLAM | Light Detection And Ranging / Simultaneous Localization & Mapping | 레이저 거리측정 / 동시 측위·지도화 |
| AiP | Approval in Principle | 원리승인 (선급 사전승인) |
| NTQ | New Technology Qualification | 신기술 자격인증 (ABS) |
| HAZID / HAZOP | Hazard Identification / Hazard & Operability Study | 위험식별 / 위험·운전성 분석 (IEC 61882) |
| FMEA / FMECA | Failure Mode (and Effects) (and Criticality) Analysis | 고장모드·영향(·심각도) 분석 (IEC 60812) |
| ESD | Emergency Shutdown | 비상정지 (IEC 61511) |
| ATEX | ATmosphères EXplosibles | 폭발성 가스 환경 — EU 방폭 지침 (Directive 2014/34/EU) |
| IECEx | IEC System for Certification to Standards Relating to Equipment for Use in Explosive Atmospheres | 국제 방폭 인증 체계 |
| EMI / EMC | Electromagnetic Interference / Compatibility | 전자파 간섭 / 적합성 (IEC 60533) |
| SL | Security Level | 사이버보안 등급 (IEC 62443-3-3 SL 1~4) |


## 신기술 범주

### 개요 (목적·범위)

**목적**
- 2025~2030 사이 선박 전기설비 분야에서 **프로토타입이나 상용화가 진행 중인 신기술**을 한눈에 정리한다.
- KR 규칙 개정·플랫폼 구축·서비스 개발(3장)의 **입력 자료**로 활용한다.
- IACS·선급별 인증 동향(AiP·NTQ·형식승인)을 추적하여 KR의 대응 속도를 가늠한다.

**범위 (3대 범주)**

| 범주 | 포괄 영역 |
|---|---|
| **A. 전력변환·배전 혁신** | MVDC, WBG(SiC/GaN), DC 그리드, DC 차단기, OPS/HVSC/LVSC, 전압등급 전략 |
| **B. 청정 에너지원·저장** | 배터리(화학별 TRL), 대형 ESS, 열폭주 전파방지, 연료전지, 대체연료 발전기, 보조전력 |
| **C. 디지털화·AI·통합** | 디지털 트윈/스레드, AI EMS·PMS, APM, 검사 자동화, MASS·ROC, IAS(TSN·IEC 61850) |

### 전력변환·배전 혁신

| 카테고리 | 핵심 기술 / 사양 | TRL | 대표 실선·인증 사례 |
|---|---|---|---|
| **MVDC (Medium Voltage DC)** | 공통 DC 버스 배전, IEEE 1709-2018 (1~35 kV) | 6~8 | ABB PSV Dina Star (2013, Onboard DC Grid 세계 첫 상용), HD현대 Breakerless MVDC **ABS NTQ 세계최초(2025.8)**, HD현대 30 MW SOFC+MVDC VLCC LR AiP(2023.10) |
| **전력반도체 (WBG)** | SiC MOSFET(1.2~10 kV 추진·대전력) / GaN HEMT(650~900 V 보조) / SST | SiC 6~8, GaN 4~6, SST 3~5 | GE Vernova VDM25000 (SiC) |
| **DC 그리드 아키텍처** | 통합 DC 배전 시스템 | 8~9 | ABB Onboard DC Grid, Siemens BlueDrive PlusC (체적·중량 30%↓, Edda Freya 연료 15~20% 절감), Wärtsilä LLC (5~45 MW, 효율 2~3%↑) |
| **DC 차단기·아크 보호** | Hybrid DCCB / SSCB / Mechanical DCCB | Hybrid 6~8, SSCB 5~7, Mech 8~9 | Hitachi Energy (Hybrid), ABB SACE Infinitus (SSCB). 참조표준: UL 1699B + IEC 63027:2023 (※ PV 전용 — 선박은 IEC 60092-202/-401·IEEE 1709 보완 필요) |
| **육상전원 (OPS/HVSC/LVSC)** | 정박 중 항만 전력 (LVSC ≤1 kV / HVSC >1 kV) | — | IEC/IEEE 80005-1:2019+AMD2:2023, **80005-3:2025 LVSC 정식 국제표준**, IACS Rec.182(2024), WPT(MF Folgefonn 1 MW) |
| **DC 전압등급 전략** | 상선 1~10 kV / 함정·초대형 IFEP 6~20 kV | — | KR 우선 감시 구간 |

**상세 설명**

- **MVDC** — 발전·추진·배터리를 공통 DC 버스에 통합 배전하는 방식. AC 대비 변환 단수가 줄어 효율·체적·중량에서 우위이고, 발전기 가변속 운전이 가능해 부분부하 연료 절감(5~20%)이 크다. 약점은 DC 차단의 어려움(영전류 통과 부재)과 선박 DC 아크 보호 표준의 미성숙 — 보호협조 설계가 핵심 리스크.
  - **KR 내부 인식**: HD현대 Breakerless MVDC가 ABS NTQ 세계최초(2025.8)로 인증되며 상용화 임계점을 통과한 반면, **KR은 MVDC 보호협조·차단·아크 보호에 대한 세부 노테이션·검사기준이 부재**한 상태. 표준·노테이션 공백을 *가장 시급한 KR 우선 정비 과제*로 인식 — 3장 5-1(기술기준 정비)·5-3(검사 자동화)·5-4(HIL/DT 가상시운전)와 직결.
- **전력반도체 (WBG)** — Silicon 대비 광대역 갭을 가진 SiC·GaN 소자. 저손실·고온·고주파 동작이 가능해 인버터 효율 1~3%↑, 체적·중량 절감, 냉각 단순화. SiC는 추진·대전력(중·고전압), GaN은 보조전원·DC-DC(중·저전압) 용도.
- **DC 그리드 아키텍처** — AC 발전기를 직접 결합하는 전통 방식이 아닌, 발전기→정류기→DC 버스→인버터→부하의 토폴로지. 발전기 가변속·다발전기 부하분담이 자연스럽고, 응답 빠른 ESS 통합이 용이.
- **DC 차단기·아크 보호** — AC와 달리 영전류 통과(zero crossing)가 없어 DC 전류 차단이 본질적으로 어렵다. **Hybrid DCCB**(기계 + 반도체 결합, ms급)와 **SSCB**(전반도체, μs급 고속) 두 방식이 경쟁 중. 선박 DC 아크 보호 표준은 UL 1699B/IEC 63027이 PV 전용이라 별도 보완이 필요.
- ~~**통합 전기추진 (IFEP)**~~ — 함정·크루즈선에서 채택된 통합 전기추진 개념. 본 로드맵에서는 별도 카테고리 대신 MVDC·DC 그리드 아키텍처에 통합 처리(중복 회피).
- **육상전원 (OPS/HVSC/LVSC)** — 정박 중 선내 발전기 대신 항만 전력을 수전 → 배기·소음 0. IEC/IEEE 80005 시리즈는 용량 기준으로 **HVSC**(>1 MVA, 컨테이너선·크루즈)와 **LVSC**(<1 MVA, 페리·소형선)를 구분(80005-3:2025 LVSC 발간). 무선 전송(**WPT**)은 Wärtsilä Folgefonn 1 MW급 inductive WPT(2017 세계최초 시연) 외엔 상용화 미정.
- **DC 전압등급 전략** — 상선은 1~10 kV(중압)에 수렴 중, 함정·초대형 IFEP는 6~20 kV까지 확장. KR이 우선 표준·검사기준을 추적해야 할 구간.

### 청정 에너지원·저장

| 카테고리 | 핵심 기술 / 사양 | TRL | 대표 실선·인증 사례 |
|---|---|---|---|
| **대형 ESS (>10 MWh)** | 컨테이너형 교체식 / Ro-Pax / 하이브리드 | 9 | COSCO Shipping Green Water 01 (700 TEU, 표준 38.4 MWh / 확장 ~80 MWh LFP, 2023.12 인도), Incat Hull 096 "China Zorrilla" (Buquebús, 40 MWh Corvus Dolphin Ro-Pax, 2025.5 진수·2026 시운전), Scandlines PR24 "Futura" (10 MWh Leclanché, 2024 운항), Brittany Ferries Saint-Malo·Guillaume de Normandie (각 12 MWh, 2024~25), Wasaline Aurora Botnia 업그레이드 (12.6 MWh, 2026 초) |
| **열폭주 전파방지(TRP) BMS** | Passive(에어로젤) / Active(오프가스 감지·수분사) | 8 | DNV-RU-SHIP Pt.6 Ch.2 Sec.1 — 셀·모듈·최종설치 3단계 시험 강제 |
| **연료전지** | SOFC / PEMFC / MCFC | SOFC 6, PEMFC 8, MCFC 5 | SOFC: HD현대 30 MW VLCC LR AiP(2023.10), Bloom Energy 65 kW ABS 형식승인(2025.9), MOL+삼성중공업 174K LNGC 300 kW SOFC(Bloom 공급) LR AiP(2025.6) / PEMFC: Ballard FCwave(200 kW/모듈, DNV TA 2022.4), MF Hydra(2×200 kW, 2023.3 상업운항), Samskip SeaShuttle 3.2 MW(eCap Marine PEMFC, 2027 운항예정) |
| **FC+배터리 하이브리드 토폴로지** | FC 정상부하 + 배터리 transient 보상 | 7 | 모든 연료전지 선박의 표준 토폴로지로 정착 중 |
| **대체연료 발전기** | 암모니아 DF / H2 ICE / 메탄올 DF | NH3 7, H2 ICE ~7, MeOH 9 | NH3: MAN-ES ME-LGIA (HD HHI EPS VLAC 2026.Q1 첫 인도), Wärtsilä 25 Ammonia (Skarv timber carrier 2026.Q4 장비·2027 진수), HiMSEN H22CDF-LA (class approval 2024.10) — 공통 이슈: 연소 불안정·구리 부식 / H2 ICE: CMB.TECH-Windcat Hydrocat 48 (2022.5 운항), Hydrocat 60 (2025), HD현대 HiMSEN 1.5 MW LNG+H2 혼소(H2 최대 25%, AiP 2022.9) / MeOH: Maersk Laura(2023.9 첫 메탄올 컨선 2.1k TEU)·Ane Maersk(2024 첫 16k TEU), 18선대 2025.5 완성 |
| **슈퍼커패시터·플라이휠** | 피크 부하 대응, 배터리 수명 연장 | 8 | — |
| **수소·암모니아 저장·공급** | 액화수소 LH2 / NH3 크래커 | 6 | LH2: Suiso Frontier 1,250 m³ (KHI, 2021.12 첫 항해), KHI-JSE 40,000 m³ (2026.1 계약, FY2030 시연) / NH3 크래커: SHI+Amogy LR AiP (2024, 88K cbm NH3 carrier, Amogy 크래커+FC), SHI+파나시아+Vinssen+MISC BV AiP (2025, ACS+PEMFC tanker), H2SITE Bertha B 30 kW PEMFC (2023.11 비스케이만 시운전) |
| **재생 보조전력** | PV / 로터세일 Flettner Rotor | PV 9, 로터 9 | Auriga Leader(PV), Viking Grace·Maersk Pelican(로터, **5~10% 연료 절감**) |

**상세 설명**

- **배터리 (화학별)** — 화학구성에 따른 *안전·에너지밀도·수명*의 트레이드오프. **LFP**가 열안정성·수명 우위로 선박 ESS 표준 자리. **NMC**는 에너지밀도가 높아 페리·하이브리드에 채택. **LTO**는 20,000회 이상 초고속 충방전 가능 — 페리 단거리·잦은 입출항에 강점. **전고체 SSB**는 액체 전해질 제거로 안전·에너지밀도 동시 향상(차세대), 2027 상용화 목표. **나트륨이온**은 cost·자원 확보 우위로 저속선·항만 stationary에 가능성.
- **대형 ESS (>10 MWh)** — 전기추진 페리·하이브리드 컨테이너선·항만 zero-emission 등에 적용. COSCO Green Water 01은 컨테이너형 50 MWh를 *교체식*으로 풀어 전기추진 컨테이너선의 임계점을 돌파. Incat Tasmania Hull 096(40 MWh Ro-Pax, 2025)은 세계 최대급 전기 페리.
- **열폭주 전파방지(TRP) BMS** — 한 셀의 폭주가 인접 셀·모듈·팩으로 번지지 않도록 차단하는 안전 통합 BMS. **Passive**(에어로젤 등 차열재)와 **Active**(오프가스 감지 + 수분사·환기)를 조합. DNV 등 주요 선급이 셀·모듈·최종설치 3단계 시험을 의무화해 사실상 인도 조건.
- **연료전지** — 화학에너지를 전기로 직접 변환 — 무탄소(H2)·저탄소(NH3 크래커·메탄올). **SOFC**는 고온·고효율(>50%)이나 응답이 느려 배터리 병행 필수. **PEMFC**는 저온·고속응답으로 단거리 페리에 적합. **MCFC**는 연구 단계.
- **FC+배터리 하이브리드 토폴로지** — FC가 평균부하를, 배터리가 transient·peak를 담당. SOFC의 ramp rate 제약과 PEMFC의 stack 보호를 동시에 해결 — 모든 연료전지 선박의 사실상 표준 구성.
- **대체연료 발전기** — 무탄소·저탄소 연료를 *직접 연소*해 전기를 생산하는 내연기관 발전기. **NH3 DF**는 2025~2026 실선 탑재 단계지만 연소 불안정·구리 부식이 미해결. **H2 ICE**는 역화·압축비 제약, 보통 혼소(diesel + H2)로 시작. **메탄올 DF**는 가장 성숙해 Maersk 16k TEU에 표준 채택.
- **슈퍼커패시터·플라이휠** — 초단기(<수초) 피크 부하 대응. 배터리의 cycle stress를 흡수해 SOH 보호 — 다이내믹 포지셔닝·thruster 급부하 선박에 효과.
- **수소·암모니아 저장·공급** — **LH2**는 −253°C 극저온 액화로 단위 부피 에너지밀도 확보, BOG 처리·재기화 시스템이 핵심. **NH3 크래커**는 NH3를 H2로 분해해 연료전지 공급 — 수소 캐리어 전략의 핵심.
- **재생 보조전력** — **PV**는 갑판 면적 한정으로 보조전력 수준(수십 kW), 자동차운반선·탱커에 보조 도입. **로터세일**(Flettner Rotor)은 매그너스 효과 기반 풍력 보조 추진으로 5~10% 연료 절감 실증, TRL 9.

### 디지털화·AI·통합

| 카테고리 | 핵심 기술 / 사양 | TRL | 대표 실선·인증·표준 |
|---|---|---|---|
| **디지털 트윈** | 자산의 가상 분신 + V&V | — | ISO 23247-1~4:2021 (프레임워크), DNV-RP-A204 (DT 신뢰성 보증), DNV-RP-0513 (시뮬레이션 모델 V&V·first-principles), DNV-RP-0510/0671 (데이터기반·AI 시스템 보증), DNV-CG-0508 (Smart vessel descriptive notation). 실선: HHI HiDTS(LNGC 174k m³, DNV DDV+DT AiP, 2022.3 → 클라우드형 AiP 2024 Gastech), DNV Veracity(11,000+척), ABS Wavesight My Digital Fleet(2024.6, data/risk platform), KR-Real360+HiDTS |
| **AI/ML 기반 EMS·PMS** | 부하예측(LSTM/Transformer) / DRL 부하분담 / 예측정비(CNN·AE) | 부하예측 8~9, DRL 5~6, 예측정비 8~9 | Wärtsilä Expert Insight(글로벌 200척+, ※ 공식 출처 미확인), ABB Predictive Intelligence, Kongsberg KM Performance(2026.2 발표) |
| **자산성능관리(APM)·디지털 스레드** | EAM↔CMS↔ERP 통합, RUL·CBM | — | ISO 55000:2024, ISO 14224, MIMOSA OSA-EAI, ISA-95 |
| **검사 자동화·원격검사** | AI 도서검토(RAG/LLM) / AR/VR/MR / 로봇·드론 | — | HoloLens·RealWear ATEX·Vision Pro, Spot·ANYmal X·Elios 3, DNV Veracity·ClassNK RSG v3.0 |
| **MASS 전력시스템** | E0/UMS (DNV/LR/ABS 무인기관실 노테이션) 기반 장기 무인운전 확장, 2N/2N+1 redundancy, Fail-Operational, 자가복구 마이크로그리드 (※ "AUT-30/90"은 공인 노테이션 아닌 개념적 확장) | — | Yara Birkeland(7 MWh, 3주년 250+ 항차·CO₂ 1,000톤/년 저감) |
| **육상 원격운항시스템(ROC)** | 형식승인 신영역, 다중화 통신 | — | MASS Code Ch.12, 위성·LTE·VDES |
| **통합 자동화(IAS)** | TSN / IEC 61850 디지털 변전소 / OPC UA Pub/Sub over MQTT | TSN 4~5, IEC 61850 7~8, OPC UA 6~7 | TS 61850-6-3 Ed.1 등 2025년 신규(※ marine 특화 5건 근거 추가 확인 필요). 시장: 2025 USD 21.5억 → 2035 USD 35.4억(CAGR 5%) |

**상세 설명**

- **디지털 트윈(DT)** — 물리 자산의 *가상 분신*. 센서·시뮬레이션·이력 데이터로 실시간 동기화. ISO 23247이 일반 프레임워크, DNV-RP-A204가 DT 신뢰성 보증, DNV-RP-0513가 시뮬레이션 모델 V&V(first-principles), DNV-RP-0510/0671이 데이터기반·AI 시스템 보증을 각각 분담. DNV-CG-0508은 V&V 가이드가 아니라 Smart vessel descriptive notation. 선박은 LNGC·DPS 등 안전·운용 가치가 큰 자산부터 적용.
- **AI/ML 기반 EMS·PMS** — 항해·정비 의사결정에 AI 도입. **부하예측**(LSTM·Transformer)은 다음 구간 부하를 예측해 발전기 기동 최적화, **DRL 부하분담**(DDPG·PPO·DQN)은 다발전기·배터리 동적 분담, **예측정비**(CNN·Autoencoder)는 진동·전류 패턴에서 결함 조기 감지. 운영 효율 5~10% 개선 기대.
- **자산성능관리(APM)·디지털 스레드** — 자산의 *상태 기반 정비·RUL 예측*을 통합 관리하는 플랫폼(APM)과, 설계→제조→운영→폐기까지 *생애 데이터를 잇는 정보 흐름*(디지털 스레드). ISO 55000:2024가 거버넌스, ISO 14224가 신뢰성 데이터 분류, MIMOSA OSA-EAI가 시스템 간 호환, ISA-95가 OT↔IT 계층 모델을 제공.
- **검사 자동화·원격검사** — 선급 검사 패러다임 전환. **AI 도서검토**는 SLD·알람리스트·보호협조표를 RAG/LLM으로 사전 검토, **AR/VR/MR**은 현장에 도면·체크리스트 오버레이(RealWear는 ATEX 인증으로 H2/LNG 위험구역 사용 가능), **로봇·드론**(Spot, ANYmal X, Elios 3)은 접근 곤란·고위험 구역 자동 검사.
- **MASS 전력시스템** — 자율운항 등급이 올라갈수록(현 선급 노테이션 E0/UMS의 무인 주기를 30~90일로 확장하는 개념. "AUT-30/90"은 정식 노테이션 아님) 사람이 현장 복구를 못 하므로 **Fail-Operational·2N/2N+1 다중화·자가복구 마이크로그리드**가 요구됨. Yara Birkeland가 3년 운용 데이터로 비용·안전성 입증. DNV AROS, ABS Autonomous and Remote-Control Functions 등 자율 노테이션이 정식 경로.
- **육상 원격운항시스템(ROC)** — 육상에서 다수 선박을 원격 제어·감시하는 센터. 위성·LTE·**VDES**(VHF Data Exchange) 다중화 통신과 사이버보안이 핵심. 형식승인 신영역으로 선급별 규칙이 정비 중(MASS Code Ch.12).
- **통합 자동화(IAS)** — 선내 OT 네트워크 차세대 표준 후보들. **TSN**(IEEE 802.1)은 결정형 이더넷이지만 선박 프로파일이 아직 없음(육상 산업 우선). **IEC 61850**은 육상 변전소 표준이 선박 switchboard로 확장 중. **OPC UA Pub/Sub over MQTT**는 위성·저대역 친화. Marine switchboard 시장은 2025→2035 약 1.6배 성장 전망(CAGR 5%).


## KR 전력설비 플랫폼·서비스 과제

### 개요 (목적·구성·원칙)

**목적**
- 2장의 신기술 동향과 별도 분석한 **규제·기술 공백**을 입력으로 받아, KR이 우선 추진할 **플랫폼·서비스·규칙·연구과제**를 액션 카탈로그로 정리한다.
- 검사·승인 업무의 디지털화·자동화를 통해 **신기술 선박의 일관성·추적성·심사 속도**를 확보한다.
- 글로벌 선급(DNV·ABS·LR·BV·ClassNK·CCS) 대비 KR의 **차별화 영역**(KR 통합, 디지털트윈 노테이션, AI 검사 보조)을 구체화한다.

**입력 → 산출 구조**
```
[2. 신기술 범주]     +     [규제·기술 공백 분석]
        │                          │
        └────────────┬─────────────┘
                     ▼
        [3. KR 액션 카탈로그]
        ├ 규칙·가이드(문서)          ← 예: Arc-Flash Guideline, KR-Smart 노테이션
        ├ 플랫폼·소프트웨어           ← 예: KR connector
        ├ 데이터·표준 모델            ← 예: 표준 알람 매트릭스 DB, mode-aware PQI
        └ 연구과제(PoC)              ← 예: MVDC/FC Preview PoC, HIL 가상시운전
```

**구성 (3대 축)**

| 축 | 절 | 핵심 산출물 |
|---|---|---|
| **3. 전력품질 모니터링·평가** | 3-1 ~ 3-4 | 선박 PQI, AI 통합 로그분석, 수소 통합 대시보드, 주파수 안정화 |
| **4. 자산관리 플랫폼** | 4-1 ~ 4-5 | EAM·APM 매트릭스, ISO 14224 taxonomy, **KR-DT-EPS** 노테이션, AI 타당성 Preview |
| **5. 검사·승인 지원 시스템** | 5-1 ~ 5-4 | 기술기준 정비, 선박-항만 인터페이스, **KR 검사 자동화**, HIL/DT 가상시운전 |


### AI 적용 매트릭스 (절별 개요)

각 세부 과제에 적용 가능한 AI 기법·모델·산출물을 한눈에 정리. *최종 판단은 검사원/설계자가 수행*하며, AI는 **검토 보조·자동초안·이상탐지** 역할로 한정한다.

| 절 | 적용 AI 기법 | 입력 데이터 | AI 산출물 | 핵심 위험 통제 |
|---|---|---|---|---|
| **선박 PQ 모니터링** | DWT+ANN 6종 분류, Park transform + ML, Isolation Forest | PQ 시계열(V·I·THD·dip), 운항모드 태그 | 이벤트 자동 라벨링, mode-aware PQI 가중치 추천 | IEC 61000-4-30 Class A 측정 결과와 교차검증 |
| **AI 통합 로그분석** | LSTM-AE(Malhotra 2016), TranAD(Tuli VLDB 2022), AnomalyBERT(Jeong 2023), LogLLM(BERT+Llama, Guan 2024) + LogRAG(Zhang ISSRE 2024) | Alarm·Event·SCADA·Trip·IR 로그 | 이상탐지·전조·RCA 초안 + LLM 자연어 요약 | 규칙기반 causal graph + ML score + LLM 3계층 (hallucination 통제) |
| **수소-전력 통합 대시보드** | Mode-aware classifier, FC degradation Transformer, AR 오버레이 (대시보드 ↔ 현장 연동) | FC stack V·I·T, BOP, H2 누설, 배터리 SoC, 3D 모델·장비 위치·태그 매핑 | 모드 자동분류, degradation 조기경보, Cause-Effect 시각화, AR Hazard Map 현장 투영, 라이브 태그값 장비 오버레이 | ISA-18.2 alarm rationalization, first-out alarm 우선, AR 오버레이는 시각 보조용 — 운전 판단은 HMI 우선 |
| **주파수 안정화** | DRL(DDPG/PPO) droop·VSG 튜닝, ROCOF 예측 | 발전기 응답, ESS PCS, 부하 시계열 | 가상관성 파라미터 추천, load-sharing 최적해 | HIL 사전 검증 필수 — DRL 직접 폐루프 금지 |
| **EAM ↔ APM 연계** | 텍스트 분류(BERT), KG 임베딩 | WO·정비이력·BOM·재고 | 작업지시 자동분류, 부품 수요예측 | ISO 55000 거버넌스 하 운영, AI는 추천만 |
| **핵심 기능 모듈** | CNN(IR 열화상), VMD+Bi-LSTM(진동), 전이학습 | 열화상, 진동, DGA, PD, 절연저항 | 결함 자동 라벨, RUL 점수, 정비시점 추천 | 정비원 final-call, AI 신뢰도(uncertainty) 표시 |
| **데이터 모델 표준** | LLM 스키마 매핑, NER | ISO 14224 / MIMOSA / ISA-95 문서, 선박 태그 | 태그 자동 매핑 초안, 갭 리포트 | 인용 무결성 검증, 사람 승인 후 반영 |
| **솔루션 매트릭스** | LLM 비교분석 + RAG | 벤더 자료, 도입 사례, 사용자 피드백 | 벤더 적합도 카드, ROI 시나리오 | 출처 표기 필수, 광고성 자료 가중치 down |
| **AI 타당성 Preview** (★) | **RAG/LLM 사전검토 보고서**, 규정 자동매핑, 갭 분석 | 기술제안서, SLD, P&ID, 인증사례 DB | AiP 사전검토 보고서 초안, 갭 매트릭스, 위험 카드 | 인용 무결성 모듈, 검토자 워크플로우 |
| **기술기준 정비** | LLM 규칙 비교(KR ↔ DNV/LR/ABS/IEC) | KR·IACS·선급 규칙 원문 | 미보유 지침 갭 매트릭스 초안 | 규칙 원문 인용 강제, 사람 작성·승인 |
| **선박-항만 인터페이스** | LLM 법령·표준 cross-walk | IEC 80005, ISO 20519, 국내법 | 법령 충돌·공백 리포트 | 법률 검토자 최종 확인 |
| **검사·승인 자동화** (★) | **AI 도서검토(RAG/LLM)**, AR 오버레이, OCR+NER, 이미지 인식 | SLD, 알람리스트, 보호협조표, 현장사진 | 규칙 갭 리포트, 알람 매트릭스, Punch List, 위치기반 가이드 | Rule Engine 우선·LLM 보조, 검사원 final-call |
| **HIL·디지털 트윈 시험** | Surrogate ML(ROM 가속), DRL 시나리오 생성, FMU 자동조립 | DT 모델, HIL 측정, 시나리오 라이브러리 | 시험 케이스 자동 추천, 결과 자동 분류 | DNV-RP-0513(시뮬레이션 모델 V&V) / DNV-RP-0671(AI 시스템 보증) 준수 |

**KR 공통 인프라 (절 횡단)**
- **벡터DB**: KR 규칙 + IACS UR + IEC/IEEE/ISO + AiP/NTQ 이력 → 모든 RAG 모듈이 공유
- **LLM 게이트웨이**: 인용 무결성 검증·hallucination 통제·감사 로그
- **MLOps 파이프라인**: fleet baseline 재학습, 모델 버전·드리프트 관리
- **사람-AI 협업 UI**: 초안 → 검토 → 수정 → 승인 워크플로우 표준화


### Power Quality Monitoring and Assessment

#### 선박 전력품질 모니터링 및 평가

**측정 항목 (육상 대비 선박 특이성)**

| 항목 | 선박에서 특히 중요한 이유 | 대표 원인 |
|---|---|---|
| 전압 THD / 개별 고조파(5/7/11/13차) | 전력전자 부하 비중↑ | 추진 인버터, bow thruster VFD, 배터리 PCS |
| 전압강하(dip)·순간 주파수 편차 | 발전기 관성·용량 여유 작음 | 대형 펌프 기동, thruster 급부하 |
| 전압 불평형 (VUF) | 모터 발열·토크 맥동·컨버터 전류 왜형 | 비대칭 부하, 배선 임피던스 차이 |
| 인터하모닉·고주파(수 kHz~) | 주파수 드리프트로 FFT 가정 깨짐 | VFD 스위칭, AFE, 케이블 공진 |
| 필터 고장 후 허용 운전모드 | 선급 규정상 명시 필요 | 수동/능동 필터 trip, 커패시터 손상 |
| DC ripple·sag·arc | DC 그리드 도입 확대 | DC bus, DC/DC, ESS PCS |

**표준 매핑**
- `IEC 61000-4-30 Class A` 측정 알고리즘·집계 방식 (계측기 핵심 스펙)
- `IEC 61000-2-4` 산업용 호환성 레벨 → 선박은 내부 PCC 기준으로 재해석
- `IEEE 519` PCC 고조파 제한 → 선내 PCC(발전기·주배전·대부하 접속점) 정의 필요
- `IACS UR E24` THD 8% 한도, 주버스 연속모니터링, 연 1회 측정, 필터고장 sea trial 검증
- `IEC 60092-101` 선박 전기설비 일반 요구
- `KR Rules Pt 6 (2025)` 전압 THD ≤ 8%, 개별 고조파 ≤ 5%

**선박 PQI 설계 (단일 표준 부재 → 운영용 KPI 가중합 권장)**
```
PQI = w1·THD + w2·VUF + w3·dip severity + w4·f deviation + w5·event count
- 운항모드별 가중치 차등: DP / 접안 / 하역 / 항해
- 필수부하 영향 가중:     추진·조타·항해장비 > 호텔부하
```

**분석 기법 (선박 적합도)**

| 기법 | 용도 | 비고 |
|---|---|---|
| FFT / True RMS | 정상상태 THD·KPI | 기본 (주파수 드리프트 보완 필요) |
| STFT / Wavelet (DWT) | dip·notch·transient 분리 | 하이브리드 페리·배터리선 우수 |
| Park transformation | 불평형·역상·토크맥동 시각화 | 추진 드라이브 중심 선박 유리 |
| S-transform | 위상 보존 + ML feature | 이벤트 분류·RCA 보조 |
| Periodicity-independent (Aalborg) | 주파수 드리프트 강건 측정 | 고립계통 선박에 적합 |
| DWT + ANN (6종 분류) | disturbance 자동 분류 | hybrid ferry 실증 |

**기술 발전 방향 (~2030)**
- Edge AI 이벤트 분류 → 위성통신 절감 (필요시만 원본 전송)
- 무선 PQ 센서 → 임시 계측·증설 (CT/VT 안전성 검토 필수)
- DC PQ 표준화 (ripple, sag, arc, ROCOC 지표)
- PMS/EMS 폐루프 연계: PQ → load shedding / generator dispatch / battery PCS ramp

**수소에너지 선박 적용 특이성 (FC + 배터리 하이브리드)**

| 영역 | PQ 특이 이슈 | 권장 모니터링 |
|---|---|---|
| FC stack 출력 | DC ripple (BOP·purge 영향), 셀 V 편차 → degradation 지표 | DC bus V/I·ripple FFT + 셀전압 dispersion |
| FC 동적 응답 한계 | ramp rate 제약 → 급부하 시 배터리 의존, DC bus sag·ROCOC 증가 | 배터리 PCS 전류·DC bus dV/dt 동시 트렌드 |
| BOP (압축기·송풍기·냉각펌프·humidifier) | 신규 VFD 고조파·인터하모닉·EMI 소스 | feeder THD/IH + 모터 베어링 전류·EMI 스펙트럼 |
| DC/DC·인버터 단 | SiC 고주파 스위칭 ripple, 케이블·필터 공진 | 수 kHz~수십 kHz 대역 PQ + dv/dt·di/dt |
| 모드 천이 | cold start / harbor zero-emission / transient peak / FC-only / battery-only / degraded 별 PQ 특성 상이 | mode-aware PQI (운전모드 태그와 결합 집계) |
| 안전 인터록 | H2 누설 → ESD → 부하 차단 시 전압 dip·주파수 편차 | PQ event log ↔ ESD Cause & Effect 동시 분석 |
| 위험구역 계측 | IEC 60079 hazardous area 내 본질안전 요구 | Ex ia/Ex d 인증 PQ 센서·광아이솔레이션 CT/VT |

**추가 표준 (수소 특화)**
- `IEC 62282` 시리즈 — 연료전지 안전·성능·모듈
- `IMO MSC.1/Circ.1647` — 연료전지 interim guidelines (2022.4 승인 / 2022.6.15 회보)
- `IGF Code` + `SOLAS II-1/55` 대체설계승인
- `IEC 60079` — Ex 등급 (PQ 계측기·CT/VT·배선 선정)
- `ISO 19847 / 19848` (2024.2 개정) — FC stack·BOP·H2 safety 태그 네이밍·데이터 서버

**PQI 보정 (수소 하이브리드 운영용)**
```
PQI_H2 = PQI_base
       + w6·(FC ramp 부족분 → battery 보상 transient)
       + w7·(DC ripple severity)
       + w8·(mode-transition 빈도·dip)
- mode 가중치: cold start > 모드천이 > FC-only ≈ battery-only > harbor
- 안전 이벤트와 PQ event 시각 동기화 필수 (RCA 결합)
```

→ **연계점**: 3-3(수소-전력설비 통합 대시보드)·5-3(검사 자동화)와 태그·이벤트 모델 공유, mode-aware PQI를 가스 누설·ESD 시퀀스와 정합 검토. 3-4(주파수 안정화)의 VSG·ROCOF 협조와도 연결.

#### AI를 활용한 전력 설비 통합 로그 분석

**데이터 소스 (멀티모달)**
- `Alarm log` — 과전류·절연저하·과온·접지·breaker alarm → 고장 라벨로 활용
- `Event log` — breaker open/close, synchro, load shedding, blackout, mode transfer → RCA의 순서 정보 핵심
- `SCADA/PMS 시계열` — V·I·f·P·Q·THD·SOC·온도·진동 (sub-second~초)
- `보호계전기 trip log` — trip cause, pickup, SOE, COMTRADE 파형 → 고장 모드 분류
- `IR thermography` — hotspot ΔT·상대온도·열분포 entropy → 이미지 + 특징량 융합

**알고리즘 스택**

| 계층 | 모델 | 용도 |
|---|---|---|
| 1차 스크리닝 (Edge) | Isolation Forest | 희소 이벤트·집계 특징량 |
| 다변량 정상 학습 | Autoencoder + Mahalanobis | PMS 정상 프로파일 (Fera & Spandonidis 2024) |
| 시퀀스 의존 패턴 | LSTM-AE (Malhotra 2016) | trip 직전 전조 탐지 |
| 모드 인식 / 장기 의존 | TranAD (2022), AnomalyBERT (2023) | 운전모드 가변형 mode-aware |
| RUL 예측 | Trans-Lighter (2023) | 베어링·절연·접점·냉각팬 |
| 고장 분류 (선박 추진) | VMD + Multi-scale PCA + Bi-LSTM (Ma 2023) | stator·bearing·insulation·cooling |
| LLM RCA 보조 | LogLLM (2024), RCACopilot, GPT-4 RCA | 자연어 요약 + RAG (FMEA·OEM 매뉴얼) |

**배포 아키텍처: 3계층 RCA(root cause analysis)**
```
[규칙 기반 causal graph] + [ML anomaly score] + [LLM 설명 생성]
        ↑                       ↑                     ↑
   FMEA/보호협조           AE·LSTM·Transformer    RAG: 매뉴얼·정비이력
```
LLM 단독은 hallucination 위험 → 위 3계층 결합이 안전.

**Edge-Cloud 파이프라인**
```
PMS/IAS/IED/VFD/BMS → Modbus·CAN·NMEA·IEC 61850 → Edge gateway
   (태그표준화·결측처리·단위변환)
→ Edge AI (10s rolling feature, FFT/THD, breaker count, alarm burst)
→ MQTT / Sparkplug B / OPC UA PubSub  (위성·저대역 친화)
→ Cloud data lake → fleet baseline → MLOps 재학습
```

#### 수소-전력설비 통합 대시보드

**데이터 모델 계층화 (선급 친화)**
```
선박 통합 계층 :  ISO 19847 (data server) + ISO 19848 (data naming) — 둘 다 2024.2 개정판
패키지 연동   :  OPC UA (FC stack, BOP, BMS, converter, ventilation PLC)
보호·IED·PMS  :  IEC 61850 (제한 적용, switchboard 영역만)
```

**모니터링 태그 그룹**

| 그룹 | 핵심 태그 |
|---|---|
| FC Stack | PEMFC/SOFC stack V·I·P, 셀 편차, 온도 분포, 절연저항, degradation 지표 |
| BOP | air supply, H2 압력/유량, humidifier, 냉각수 in/out, purge, reformer 상태 |
| H2 Safety | H2 누설 농도, 센서 self-check, double block & bleed, vent mast, purge |
| Battery/ESS | SoC·SoH, cell V spread, rack 온도, BMS 경보, available power |
| DC Power | DC bus V/I, ripple, insulation monitoring, fault current event |
| Propulsion | 모터 토크/속도/권선·베어링 온도, 인버터 효율·fault code |
| Mode 로그 | cold start / harbor zero-emission / transient peak / FC-only / battery-only / degraded |

**핵심 화면 3종 (도입 초기 안전 우선)**
- `Hazard Map` — H2 hazardous area (IEC 60079) overlay, 센서·환기·vent·차단밸브 표시
- `Safety Cause-Effect` — 가스 감지 level → 환기 fan auto → fuel valve close → FC shutdown → bus isolation 시각화
- `Barrier Health` — 센서 alive/fault/cal overdue, ventilation 가용성, ESD loop health, UPS 상태

**UX 원칙 (ISA-18.2)**
- 화면 상단 상주: 안전 센서 상태 + bypass 여부 (missed alarm > false alarm)
- stack 전압은 평균 + min/max/cell spread 동시 표시
- alarm rationalization·shelving·flood 방지·first-out alarm 강조
- `commissioning mode / degraded mode / post-trip replay` 화면 분리

**SW 스택 (운영 HMI ↔ 분석 대시보드 분리)**

| 계층 | 후보 | 적합도 |
|---|---|---|
| Class-grade 운영 HMI | Kongsberg K-Chief, ABB 800xA | 대형선·고신뢰 |
| SCADA/HMI 통합 (초기 실증) | Inductive Automation Ignition | 균형 |
| 분석·트렌드·KPI | Grafana | 빠른 PoC |

**AR 연동 계층 (대시보드 ↔ 현장 오버레이)**
- 목적: 운영 HMI의 라이브 태그값(H2 누설 농도, FC stack V·I·T, 배터리 SoC, ESD loop)을 현장 장비 위에 위치기반 오버레이 → 검사·정비 시 화면 전환 없이 현장에서 즉시 확인
- 데이터 흐름: OPC UA / ISO 19848 태그 → AR 게이트웨이 (REST/GraphQL) → AR 기기 (HoloLens 2, RealWear, Vision Pro)
- 핵심 화면 오버레이: `Hazard Map`(IEC 60079 위험구역), `Cause-Effect`(가스감지 → 환기 → 차단 시퀀스), `Barrier Health`(센서 alive/fault) 세 화면을 AR로 현장 투영
- 안전 가드레일: AR은 시각 보조용에 한정 — 운전 판단·차단 조작은 클래스급 HMI 우선, AR-only 운전금지. 방폭 구역은 RealWear ATEX 기기로 한정 (HoloLens·Vision Pro 방폭 불가)
- 5-3-1 AR/VR/MR 기반 검사지원과 공통 인프라 공유 (3D 모델·LiDAR 정합·태그 매핑)


#### 전력 주파수/DC 버스 안정화
- 발전기 관성·AVR/governor 응답 + ESS/슈퍼커패시터 가상관성(VSG)
- ROCOF 보호 협조, droop control, PMS load-sharing 최적화
- DC 그리드: 가상 droop, virtual inertia emulation by ESS PCS


### 전력설비 자산관리 플랫폼

#### EAM vs APM 개념

| 구분 | EAM (Enterprise Asset Management) | APM (Asset Performance Management) |
|---|---|---|
| 핵심 기능 | 자산등록·작업지시·정비이력·재고·구매·비용·규정준수 | 상태감시·신뢰성·중요도·예지정비·RUL |
| 데이터 성격 | 트랜잭션·문서 | 시계열·이벤트·진단 |
| 의사결정 | "무엇을 누가 언제 정비할지" | "왜·언제·어느 수준으로 정비할지" |
| 선박 전력설비 적용 | 발전기 PM WO·차단기 예비품·배터리 이력 | 절연저하·온도상승·PD·진동 → 정비시점 조정 |

**프레임워크**: `ISO 55000:2024` — 조직 목표 → 자산관리 정책 → SAMP → 라이프사이클 실행 → 성과/리스크/비용 최적화. 선박은 *안전성·가동률·클래스 준수·에너지 효율·정비비* 5축으로 번역.

#### 핵심 기능 모듈 (전력설비 매핑)

| 모듈 | 전력설비 적용 |
|---|---|
| Asset Register | `선박 > 전력계통 > 발전/배전/저장 > 설비 > 부품` 계층 (예: MV SWBD > feeder breaker > relay > CT/PT) |
| BOM / As-maintained | 시리얼·교체이력·펌웨어·릴레이 setting 추적 |
| PM / CM / CBM | 발전기(진동·절연·윤활유), 변압기(권선온도·DGA), SWBD(열화상·PD·접점), 배터리(SOH·내부저항·셀불균형), 케이블(절연저항·hotspot) |
| Critical Spares | 트립유닛·보호계전기·AVR·BMS·배터리 모듈 — 리드타임 + 중요도 매트릭스 |
| Inspection | 모바일 체크리스트, 열화상·절연시험 성적서, 클래스 제출 증빙 |
| KPI Dashboard | MTBF·MTTR·availability·반복고장률·정비백로그·spare fill rate |

#### 데이터 모델 표준

| 표준 | 역할 |
|---|---|
| `ISO 14224:2016` | 신뢰성 데이터 분류 (원래 O&G용) → 선박 전력설비 taxonomy 보완 참조 |
| `MIMOSA OSA-EAI` | EAM ↔ historian ↔ CMS ↔ ERP ↔ class 플랫폼 통합 데이터 모델 |
| `IEC 62264 / ISA-95` | OT (PMS/IAS/EMS) ↔ IT (EAM/APM/ERP) 계층 정의 |


#### 디지털 트윈 기반 자산관리

**5단계 성숙도**: Descriptive → Diagnostic → Predictive → Prescriptive → Autonomous (선박은 Predictive~Prescriptive가 현실적)

**모델링 스택**
- `Modelica` 다물리 (전기-열-제어) — 발전기·추진·열관리 연성
- `MATLAB/Simulink` 제어기·상태추정·고장진단
- `ANSYS Twin Builder` 3D/1D + ROM, 배터리·전력전자
- `FMI/FMU` 다툴 모델 교환 표준 — 발전기(Modelica)·제어(Simulink)·열(ANSYS) 통합

**설비별 하이브리드 모델**

| 설비 | 물리 모델 | 데이터 모델 | 진단 목표 |
|---|---|---|---|
| 발전기 | dq + 철손/동손 + 베어링/절연 열화 | 진동/전류 시그니처 ML | 절연열화·편심·베어링 |
| 변압기 | 등가회로 + hotspot 열모델 + 절연지 열화 | DGA·PD 시계열 | 사이클·환기 영향 |
| 스위치보드 | 접점저항·busbar 열분포·arc risk | 이벤트 로그 이상탐지 | 접점열화·국부 발열 |
| 배터리 | ECM 또는 electro-thermal + SOC/SOH/SOP | 충방전 이력학습 | 열폭주 위험 (DT 가치 ★) |
| 케이블 | I-T-Ta ampacity + 절연노화 | 종단부 hotspot·누설전류 | 절연 잔여수명 |

**실선 / 산업 사례**
- `DNV OSP` — 해양 공동시뮬레이션 기반 (Kongsberg·NTNU·SINTEF)
- `Wärtsilä Operim` product-rooted DT, `Expert Insight` AI+rule PdM
- `Kongsberg Kognifai / Vessel Insight / iEMS` — 데이터 인프라 + 에너지 최적화
- `Siemens Xcelerator` — HD현대 2026.2.16 파트너 선정, digital thread

**KR 액션 권고**
- 우선 자산: 배터리 → 발전기 → 스위치보드 순 (ROI/위험도 기준)
- `KR-DT-EPS` 노테이션: ISO 23247 + DNV-RP-A204 + CG-0508(V&V) 매핑
- HIL/PHIL 시험베드 결합 가상시운전 인정 절차 (5-4와 연결)

#### AI 기반 신기술 타당성 분석 Preview 자동작성

자산 라이프사이클의 도입(acquisition) 단계에서, 신기술(MVDC, 연료전지, NH3·H2 DF, 대형 ESS, MASS 전력시스템 등)의 AiP/형식승인 사전검토 Preview를 AI로 자동 작성. DT 모델·과거 인증사례·규정·위험 시나리오를 RAG/LLM으로 종합하여 검토자가 수일 안에 확인할 수 있는 사전검토 보고서를 생성한다 (사람-AI 협업, 최종 판단은 검토자).

| 모듈 | 기능 | 입력 | 출력 |
|---|---|---|---|
| 규정·표준 자동매핑 | 적용 IMO/IACS UR/선급/IEC/KR 규칙 추출·조항 인용 | 기술제안서, SLD/P&ID, 사양서 | 적용규정 리스트 + 인용 근거 |
| KR 갭 자동분석 | 보유/미보유 지침 자동 대조, 외부 선급 보완 매핑 | 적용규정, KR 규칙 DB | 갭 매트릭스, 미정합 항목 |
| 유사 AiP/NTQ RAG | KR·DNV·ABS·LR·BV 인증사례·승인조건 검색 | 기술 키워드, 토폴로지 | 유사 사례 카드, 보완요구 이력 |
| 위험 시나리오 추출 | HAZID/FMEA + DT 시뮬레이션 결합, 정량 지표화 | 위험분석서, DT 모델, 보호협조 | 위험 카드, HIL/PHIL 시험 권고 |
| Preview 자동생성 | LLM 사전검토 보고서 초안 + 인용 무결성 검증 | 위 4개 모듈 통합 | Preview 보고서(MD/PDF), 신뢰도 지표 |

Preview 보고서 표준 구성: ① 기술 개요·토폴로지 → ② 적용규정 매트릭스 → ③ KR 갭 → ④ 유사 인증사례 → ⑤ 위험 시나리오 → ⑥ 보완 요구사항(도면·시험·HIL/PHIL) → ⑦ AiP 사전판단(적합/조건부/추가검토) → ⑧ 인용 근거·모델 버전·검토 이력

→ 5-3 검사·승인 지원과 분리: 5-3은 AiP 이후 도면승인–현장검사–시운전 자동화. 본 모듈은 AiP 이전 타당성·사전검토 단계 자동화. 동일 RAG/LLM·지식베이스 인프라 공유, 워크플로우·산출물은 별도.
→ DT·HIL 연계 (5-4): 위험 시나리오를 HIL/PHIL 가상시운전과 결합하여 정량 근거 확보, AiP 가상검증 정식 인정 절차의 입력으로 활용.

**KR 단기 과제 (Preview 모듈)**
- MVDC·연료전지 2개 기술 대상 Preview 자동생성 PoC
- KR 규칙·IACS UR·IEC·AiP/NTQ 이력 벡터DB 구축
- 인용 무결성 모듈 (LLM hallucination 통제)
- 검토자 협업 UI MVP (초안 검토·수정·승인 워크플로우)


### 전력설비 검사 및 승인 지원 시스템

#### 기술기준 정비 (KR 미보유 지침 갭 반영)

| 항목 | 현황 | 산출물 |
|---|---|---|
| Arc Hazards (전기 아크 위험) 전용 가이드 | LR Sec 8 보유, KR은 HV Sec 15 內 부분 인용 | KR Guideline for Arc-Flash Risk Assessment (IEEE 1584 기반) |
| 알람·모니터링 매트릭스 부록 | DNV Pt.4 Ch.8 App A 보유, KR 부재 | KR Pt 6 부록 신설 (장비별 알람·트립·인디케이션 표준 리스트) |
| KR Procedure 시리즈 (ShipRight형) | LR ShipRight 보유 (도면승인–현장검사–시운전 추적 구조), KR 절차서 체계 미흡 | HV / 전기추진 / 배터리 / 연료전지 분야별 통합 절차서 (5-3 검사 자동화 워크플로우와 정합) |
| 하이브리드 전기시스템 본 규칙 섹션 | LR Sec 24(2024) 신설, KR 별도 가이던스 일부 | KR Pt 6 Ch 1 신규 섹션 (디젤+배터리+ESS 페일세이프) |
| 스마트십 세분화 노테이션 | CCS `I-Ship` 6영역, KR 노테이션 세분화 부족 | `KR-Smart` 모듈식 노테이션 (NAV/MACH/ENE/PLT) |

#### 선박-항만 인터페이스 기술기준 (규정공백 반영)

| 항목 | 갭 유형 | 산출물 |
|---|---|---|
| AMP 인터페이스 4종 (플러그·케이블·ESD·통신) | 진성공백 | IEC/IEEE 80005-1 §5~7 국내 검사기준 신설 |
| 벙커링 호스·매니폴드·ERC | 진성공백 | ISO 20519(LNG) / ISO/TS 5012(H2) / ISO/PAS 24257(NH3) 도입 |
| 선박용 수소·암모니아 탱크 이중적용 해소 | 중복적용 | 선박안전법 §26의X 신설 (자관법 §35의12 모델) |
| AMP 변환장치 표준 정합화 | 분산+미정합 | 전기사업법 §65 ↔ IEC 80005-1·3 매핑 |
| 항만대기질법 친환경연료 목록 (암모니아) | 위임공백 | 시행규칙 §7② 부령 개정 |

#### 신기술 검사·승인 지원 자동화

신기술 선박 전기설비는 MVDC, ESS, 연료전지, OPS, 사이버보안, MASS 등으로 검사·승인 범위가 확대되고 있으나, 도면·알람리스트·PMS/EMS 로직·현장검사 기록이 분산되어 있어 검사·승인 일관성과 추적성 확보가 어려움. 이에 따라 KR 규칙·국제표준·선급 가이드·프로젝트별 승인조건을 지식베이스화하고, 도서검토–현장검사–시운전–승인조건 관리까지 연계되는 **AI 기반 검사·승인 지원 자동화 체계**를 구축한다.

| 자동화 영역 | 주요 기능 | 입력자료 | 산출물 |
|---|---|---|---|
| **AI 기반 도서검토 보조** | 단선도, 결선도, 알람리스트, 보호계전기 설정값, EMS/PMS 로직의 규칙 적합성 자동검토 | SLD, 회로도, 알람·트립 리스트, 보호협조표, 부하분석서 | 규칙 갭 리포트, 질의사항 리스트, 승인조건 초안 |
| **알람·트립 매트릭스 자동검증** | 장비별 필수 알람·트립·인디케이션 누락 여부 확인, MASS Ch.8 알람관리와 연계 | 알람리스트, IAS 태그목록, 장비 데이터시트 | 표준 알람 매트릭스, 누락·중복·등급오류 검출표 |
| **전력계통 보호협조 검사지원** | MVDC/DC Grid, ESS, 연료전지, 추진 인버터 보호협조 및 차단 시퀀스 검토 | 보호계전기 설정, DC 차단기 사양, 단락해석 결과 | 보호협조 검토표, 위험 시나리오별 검사 체크리스트 |
| **ESS·연료전지 안전검사 자동화** | BMS, TRP, 환기, 가스감지, ESD, 비상차단 로직의 규칙 적합성 확인 | BMS 로직, P&ID, FMEA, HAZID/HAZOP, ESD Cause & Effect | ESS/FC 안전검사 체크리스트, 위험기반 검사 항목 |
| **OPS/AMP 인터페이스 검사 자동화** | IEC/IEEE 80005 기반 플러그, 케이블, 접지, 통신, ESD 연동 확인 | AMP 회로도, 접속 시퀀스, 통신 프로토콜, 항만 인터페이스 문서 | 선박-항만 인터페이스 검사표, 부적합 항목 리포트 |
| **모바일 현장검사 도구** | 검사원이 현장에서 태블릿·모바일로 장비 QR/RFID 인식, 체크리스트 수행, 사진·계측값 자동 기록 | 장비목록, 승인도면, 검사 체크리스트, 현장 사진·계측값 | 전자 검사기록, Punch List, 검사 이력 DB |
| **AR 기반 현장검사 보조** | 실제 장비 위에 승인도면, 케이블 경로, 차단기 번호, 검사 포인트를 오버레이 | 3D 모델, 장비 위치정보, 승인도면, 자산 DB | 위치기반 검사 가이드, 오시공·누락 식별 |
| **승인조건·이슈 추적관리** | AiP, 형식승인, 도면승인, 현장검사, 시운전 단계의 조건사항을 자동 추적 | 승인 코멘트, 검사보고서, Punch List, 시운전 결과 | 조건사항 Closure Matrix, 프로젝트별 검사 대시보드 |
| **검사 지식베이스/RAG** | KR 규칙, IMO, IEC, IEEE, IACS, 선급 가이드, 내부 검사사례를 검색형 지식베이스화 | 규칙·표준·가이드·내부 사례 | 검사 질의응답, 규칙 근거 자동 제시, 유사사례 추천 |
| **검사 데이터 분석** | 반복 부적합, 장비별 고장·결함 패턴, 프로젝트별 리스크를 분석하여 검사 우선순위화 | 검사 이력, 결함 DB, 장비 제조사 정보, 운항 데이터 | 리스크 기반 검사계획, 신기술별 취약점 통계 |
| **AI 기반 위험도평가** | HAZID/HAZOP/FMEA 자동생성, 위험 매트릭스 점수화, RBI/RBS 권고, 사이버 위험평가 정합 | P&ID, SLD, 운전모드, 결함·사고 DB, 표준 가이드워드, 위협 모델 | HAZID/FMEA 표 초안, 위험 매트릭스, 검사·정비 우선순위, IEC 62443 SL 갭 |

##### 구현 방향

1. **Rule-based + AI 하이브리드 구조**
   - 명확한 규칙 요건은 Rule Engine으로 자동 판정
   - 해석이 필요한 도면·로직·보고서는 RAG/LLM 기반 검토 보조 적용
   - 최종 승인 판단은 검사원이 수행하고, AI 결과는 "검토 보조 의견"으로 관리

2. **도면·알람·자산 데이터 표준화**
   - SLD, 알람리스트, Cause & Effect, 장비목록, 보호계전기 설정값을 표준 템플릿화
   - 장비 태그, 회로번호, 알람코드, 검사 항목을 공통 데이터 모델로 연결
   - 향후 KR, 디지털 트윈, HIL/PHIL 시험결과와 연계 가능한 구조로 설계

3. **검사 단계별 자동화 적용**
   - **도면승인 단계**: 규칙 적합성, 누락 항목, 인터페이스 오류 자동검출
   - **제작·설치 단계**: 장비 식별, 케이블·결선·접지 확인, 사진기록 자동화
   - **시운전 단계**: 알람·트립·ESD·PMS/EMS 동작 결과 자동 매칭
   - **운항 단계**: 결함 이력, 센서 데이터, 정비 이력을 활용한 리스크 기반 검사

##### 단기 개발 과제

| 우선순위 | 과제 | 내용 | 기대효과 |
|---|---|---|---|
| 1 | **AI 도서검토 PoC** | 알람리스트·SLD·보호협조표 자동검토 파일럿 | 도면검토 시간 단축, 누락항목 조기 발견 |
| 2 | **전기설비 표준 알람 매트릭스 DB** | 발전기, 배전반, ESS, 연료전지, OPS 장비별 알람·트립 표준화 | 검사 일관성 확보 |
| 3 | **모바일 검사앱 MVP** | QR/RFID 기반 장비 확인, 체크리스트, 사진·계측값 기록 | 현장검사 기록 디지털화 |
| 4 | **승인조건 Closure Matrix** | 도면승인 코멘트–현장검사–시운전 결과 연계 | 조건사항 추적성 강화 |
| 5 | **KR 검사 지식베이스** | KR 규칙, IEC/IEEE/IACS 요건, 내부 검사사례 검색체계 구축 | 검사원 의사결정 지원 |
| 6 | **HIL/디지털 트윈 연계 인터페이스** | PMS/EMS 시험결과와 검사 체크리스트 자동 매칭 | 가상시운전 인정 기반 마련 |

→ **KR 인프라 권고**: **KR 기반 전기설비 검사·승인 지원 플랫폼**을 구축하여, 도서검토 자동화, 모바일 현장검사, 승인조건 추적관리, 검사·승인 지식베이스, HIL/디지털 트윈 시험결과 관리를 하나의 워크플로우로 통합한다. 초기에는 알람리스트·단선도·보호협조표 자동검토부터 착수하고, 이후 ESS·연료전지·MVDC·OPS·MASS 전기설비로 적용 범위를 확대한다. 본 절은 5-1의 기술기준 정비, 5-2의 선박-항만 인터페이스, 5-4의 HIL·디지털 트윈 시험을 잇는 **검사·승인 업무 디지털화/자동화 허브** 역할을 수행한다. 자산 도입 단계의 AiP 사전검토 Preview(4-5)와는 상류–하류 관계로 지식베이스를 공유한다.

##### AR/VR/MR 기반 검사지원

**적용 시나리오 (전력설비 우선순위)**

| 시나리오 | 내용 | 전력설비 적용 예 |
|---|---|---|
| 원격 전문가 지원 | 현장 영상 공유 + 주석·텔레스트레이션 | SWBD 이상발열·트립, 변압기 절연 이상, 케이블 단자 과열 |
| On-site 검사 가이드 | SOP·토크값·절연저항 기준 시야 내 표시 + 자동 증적 첨부 | 차단기 LOTO, 절연시험, 토크 마킹 |
| VR 훈련 | 위험·접근곤란 작업 가상 반복 | 활선 금지구역 접근, 블랙아웃 대응, 절연시험 |
| As-built 검증 | 3D CAD/BIM 오버레이 + LiDAR 정합 | 케이블 라우팅, 관통부, 접지 네트워크 |

**선박/조선 사례**
- `DNV Veracity Remote Survey` — 영상 스트리밍·기록·문서 기반 원격검사
- `ClassNK Remote Survey Guidelines v3.0` — survey item별 필요 정보(라이브/녹화/정지 이미지) 명확화
- `삼성중공업` — 3D 설계데이터 기반 VR 훈련 (메탄올 DF 컨테이너선)
- `한화오션 RealBLAST` — VR 도장 전처리 훈련
- HD현대·MSC·Maersk — 전력설비 AR/VR 직접 공개 레퍼런스 부재 (선급 원격검사 흐름은 활용 가능)

**도입 장벽**
- 정합 신뢰성 (금속 구조물·반복 구획에서 공간인식 불안정)
- 데이터 최신성 (PLM/EAM 분리 시 오래된 절차 위험)
- 통신 (선내 Wi-Fi 음영, 위성지연, 망분리 → 저대역·오프라인 우선)
- PPE 호환 (헬멧·보안경·귀마개 간섭)
- 선급 증적 형식 불일치
- **제품 수명 리스크 (Dynamics 365 EOL 2026.12.31)**

##### AI 기반 위험도평가 자동화

신기술(MVDC, ESS, 연료전지, NH3·H2 DF, MASS 전력시스템 등) 도입 시 HAZID/HAZOP·FMEA·사이버 위험평가가 필수이나, 수작업 의존도가 높고 시나리오 누락·평가자별 일관성 부족이 빈번. **표준 가이드워드 라이브러리 + 결함·사고 DB + DT/HIL 시뮬레이션 + LLM/RAG**을 결합하여 위험도평가를 자동화하고, 검토자가 보완·확정하는 **사람-AI 협업형 위험분석 워크플로우**를 구축한다.

**기능 구성**

| 기능 | 입력 | 출력 | AI 기법 |
|---|---|---|---|
| HAZID/HAZOP 자동생성 | P&ID, SLD, 운전모드, IEC 61882 가이드워드 | HAZID 카드 (cause·consequence·safeguard·권고) | LLM + RAG (과거 HAZID·표준 가이드워드) |
| FMEA/FMECA 보조 | 장비목록, 고장모드 라이브러리, 결함 이력 | FMEA 표 (S·O·D·RPN·보완책) | 패턴 매칭 + LLM 보조 |
| 위험 점수화·매트릭스 | 빈도·영향도·검출성, 운전모드 가중치 | 위험 매트릭스, Top-N 위험항목 | Bayesian network, 통계 모델 |
| 사이버 위험평가 | 자산·zone/conduit, 위협 모델, IEC 62443 SL | UR E26 위험평가, SL 갭, 대응 권고 | rule + LLM 정합성 검토 |
| RBI/RBS 계획 자동화 | 위험 매트릭스, 검사 이력, 운항 데이터 | 위험 기반 검사·정비 일정·범위 | 최적화 + 위험 모델 |
| DT/HIL 시뮬레이션 결합 | 단락·아크·블랙아웃·열폭주 시나리오, FMU | 정량 영향(전류·전압·시간), HIL 시험 권고 | DT/PHIL + ML 후처리 |

**적용 영역 (선박 전력설비 우선)**
- MVDC 단락·아크·DC 차단기 협조 실패
- ESS 열폭주·BMS 고장·셀 단락·전파
- 연료전지 H2 누설·purge·환기 페일·점화원 노출
- 추진 인버터·발전기 고장모드와 redundancy
- MASS 무인기관실 자가복구·degraded mode 시나리오
- OPS 접속·접지·통신 페일·역송 위험

**연계 모듈**
- **Preview**: 위험 시나리오 추출 모듈에 정량 입력 제공 (AiP 사전검토 근거)
- **ESS·연료전지 안전검사**: HAZID/HAZOP 자동검토 입력
- **보호협조 검사지원**: 위험 시나리오별 보호협조 검증 매트릭스
- **승인조건·이슈 추적**: 위험 기반 잔여 조건 우선순위 결정
- **HIL·디지털 트윈 시험**: DT 시뮬레이션 결과를 위험 평가에 정량 반영

**구현 원칙**
- 표준 라이브러리 + AI 보조 구조 (LLM 단독 결과 ≠ 결론, 검토자 확정 필수)
- HAZID 가이드워드(IEC 61882) 정합, FMEA(IEC 60812) 정합
- 사이버 위험은 IEC 62443-3-2 위험평가 절차 정합
- 결과는 검토자 의사결정 보조, 최종 판단은 검사원·엔지니어
- 모델·프롬프트·데이터 버전 추적, 인용 무결성 검증

**단기 과제**

| 우선순위 | 과제 | 기대효과 |
|---|---|---|
| 1 | 표준 HAZID 가이드워드·시나리오 라이브러리 (MVDC, ESS, FC, NH3 DF, MASS) | 분석 일관성 |
| 2 | KR 내부 결함·사고 DB + 공개 사례 임베딩 → RAG | 유사 위험 검색 신뢰도 |
| 3 | HAZID/FMEA 자동생성 PoC (MVDC + 연료전지) | 분석 시간 -50% |
| 4 | IEC 62443-3-2 사이버 위험평가 자동매핑 모듈 | UR E26 정합성 자동검토 |
| 5 | DT/HIL 결과 위험 정량화 인터페이스 | 가상시운전 결과를 RBI 입력으로 연결 |

→ **KR 인프라 권고**: 본 모듈은 4-5 Preview·5-3 검사·승인 지원·5-4 HIL/DT 시험을 가로지르는 **공통 위험평가 엔진** 역할. 초기에는 MVDC·연료전지 HAZID 자동생성에 집중하고, 이후 ESS·MASS·NH3 DF·사이버 위험으로 확장한다.

#### 시뮬레이션 · HIL · 디지털 트윈 시험

| 항목 | 내용 | 표준·참조 |
|---|---|---|
| **시스템 시뮬레이션** | MVDC 보호협조·과도해석, EMS 부하분담, 단락·아크 시나리오 모델 | IEEE 1709, IEC 60092-504, MATLAB/Simulink·PSCAD·PLECS |
| **HIL (Hardware-in-the-Loop)** | 실 컨트롤러 ↔ 가상 전력계통 실시간 연계 시험 (PMS·EMS·차단기 제어기) | Opal-RT, dSPACE, RTDS, Typhoon HIL / DNV-RP-0513(시뮬레이션 V&V), DNV-RP-0671(AI), IEC 62443 (사이버 HIL) |
| **PHIL (Power HIL)** | 실 전력변환기(SiC 인버터·DC/DC) ↔ 가상부하 양방향 전력 시험 | KIER·KERI·HD KSOE 시험장 활용 |
| **디지털 트윈 시험** | 실선 운항데이터·센서 결합 가상 시운전, Class AiP 단계 가상검증 | ISO 23247, DNV-RP-A204(DT 보증), DNV-RP-0513(시뮬레이션 V&V), DNV DDV 노테이션, HHI HiDTS |
| **AI/ML 모델 검증** | 부하예측·예측정비 모델 데이터셋 검증, drift·robustness 평가 | DNV-RP-0510(데이터기반)·DNV-RP-0671(AI), IEC 63278(AAS) |

→ **KR 인프라 권고**: KR 內 HIL/PHIL 시험베드 + 디지털 트윈 V&V 플랫폼 구축, 신조선 AiP·형식승인 단계에서 가상시운전을 정식 인정하는 절차 신설.

### IMO MASS Code 대응

#### MASS Code 구조 (19개 챕터 중 전기설비 직접영향 6개)

| 영역 | 챕터 | KR 영향 |
|---|---|---|
| Part 2 공통원칙 | **System design** (Ch.5) | CONOPS/OE/ODD/Fallback 설계기준 |
| Part 2 공통원칙 | **Software principles** (Ch.6) | IEC 61508 SIL + V&V + OTA 통제 |
| Part 2 공통원칙 | **Alert management** (Ch.8) | 알람 매트릭스 + MSC.302(87) 정합 |
| Part 2 공통원칙 | **Connectivity** (Ch.11) | ROC↔MASS SLA, 위성·LTE·VDES 다중화 |
| Part 3 기능요건 | **Remote operations** (Ch.12) | ROC 형식승인 (육상시설 신규영역) |
| Part 3 기능요건 | **Machinery and electrical installations** (Ch.19) | 무인기관실 자가진단·자가복구·예측정비 |

#### MASS 핵심 개념 (Part 2)
- **CONOPS / OE / ODD** — 운항 개념·한계·자율기능 동작범위 → 부하 프로파일·전력 정격 기준
- **Fallback / Degraded State** — 기능저하 시 안전상태 천이 → 발전·배전 redundancy
- **Mode of Operation** — 수동/원격/자율 모드 전환 시 전력 재구성 검증
- **ROC (Remote Operation Centre)** — 육상 원격제어센터 (형식승인 신영역)
- **ROM (Remote Operation Management)** — SMS 보조요소
- **Provisional MASS Certificate** — 가증서 (ISM Interim과 구분)
- **EBP (Experience-Building Phase)** — 채택 후 운영데이터 수집기간

## 시급 우선순위

1. KR Digital Twin Class Notation 연구개발
2. MVDC 보호협조·DC차단기 시험표준 연구개발
3. AI/ML 시스템 인증 파일럿 연구개발
4. KASS·MASS Code 전기제어 표준활동 참여 필요성 
5. MASS Code 육상 원격운항센터(ROC) 가이드라인 연구개발 — 형식승인 신영역. 다중화 통신(위성·LTE·VDES), ROC↔MASS SLA, MASS Code Ch.12 정합
6. 암모니아 DF 발전기 접지·전기품질 가이드 연구개발
7. IEC 61850 marine + TSN profile 표준활동 참여 필요성

## 부록. KR 우선 검토

| 순위 | 기술 | 도메인 | 핵심 근거 |
|---|---|---|---|
| 1 | MVDC 보호협조 + DC 차단기 인증 프레임 | A | HD현대 Breakerless MVDC ABS NTQ(2025.8) |
| 2 | MW급 SOFC + MVDC + IFEP 통합 노테이션 | A+B | HD현대 30 MW VLCC LR AiP(2023.10), HD수소+HD KSOE+HHI+HMM+KR SOFC 무탄소 컨테이너선 MOU(2025.6.26) |
| 3 | 암모니아 DF 발전기 전기품질·접지 가이드 | B | 2025~2026 실선 탑재, 구리 부식·연소 불안정 |
| 4 | PMS·발전기 디지털 트윈 노테이션 (KR-DT) | C | DNV DDV·HHI HiDTS 시장 선점 |
| 5 | SiC 추진 인버터·연료전지 DC/DC 형식승인 | A | EMI·부분방전·열관리 검증 |
| 6 | OPS/HVSC-LVSC KR 가이드 (IACS Rec.182·80005-3 정합) + 자동접속·WPT 보완안 | A | 80005-3:2025 정식화, Rec.182(2024)는 케이블 OPS만 — 자동접속·WPT는 별도 작업 |
| 7 | AI/ML 시스템 인증가이드 (KR-AI-GL) | C | DNV-RP-0671(AI 시스템 보증) 선점, IEC 63278(AAS) 정합 |
| 8 | MASS Code Ch.19 전기·제어 매핑 + 자율운항 노테이션(DNV AROS·ABS Autonomous 정합) | C | MSC 111 채택(2026.5), 2026.7.1 발효, KASS 후속 R&D |
| 9 | 전고체 배터리(SSB) 적용 기반 가이드 | B | 2027 상용화, 덴드라이트·계면저항 고장모드 |
| 10 | NH3 크래커·LH2 저장공급 전기설비 가이드 | B | 삼성중공업+Amogy AiP, KHI-JSE 40k m³ 2030 |

