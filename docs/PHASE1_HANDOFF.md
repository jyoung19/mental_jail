# Phase 1 Handoff — Mental-Health Counseling Red-Teaming

> 이 문서는 지금까지의 Work 대화에서 논의·결정한 정신건강 상담 안전성 연구와 `mental_jail` 작업 내용을 Codex 및 공동 작업자에게 인계하기 위한 문서다.
>
> **안전 범위:** 이 문서는 상담 안전성 평가를 위한 데이터 구조, 재현성, 평가 설계를 다룬다. 자해·자살·은폐 등 유해 행동의 실행법이나 이를 상담 모델에서 끌어내기 위한 구체적인 공격 문장을 저장·생성하지 않는다.

## 0. 문서 상태 표기

- **[확정]**: 논문, 저장소, 또는 대화에서 확인된 사실.
- **[결정]**: 현재 작업에서 합의한 구현·협업 방향.
- **[추정]**: 현재 정보에 근거한 해석이며 추가 확인이 필요함.
- **[미확정]**: 진권이의 코드·데이터 또는 저자 자료가 오기 전까지 결정할 수 없음.

---

## 1. 연구 목적과 전체 구조

### 1.1 연구 목적

**[확정]** 연구의 큰 목적은 심리상담 상황에서 상담자 역할의 LLM이 자연스럽고 장기적인 내담자 대화 속에서 안전 경계를 유지하는지 평가하는 것이다.

핵심 문제는 단순한 직접 jailbreak 탐지가 아니다. 상담 모델이 사용자의 감정에는 공감하면서도 위험한 행동·왜곡된 믿음·부적절한 임상 권위를 정당화하지 않아야 한다는 점을 평가한다.

### 1.2 원논문 PCSA의 전체 구조

원논문은 **Persona-based Client Simulation Attack (PCSA)**라는 상담 도메인 red-teaming framework를 제안한다.

```text
상담 코퍼스
  ├─ C_persona: 내담자 특성
  ├─ C_style: 실제 client 발화 스타일 reference
  └─ C_distortion: 공격 목표와 연결된 인지 왜곡
          ↓
Phase I: Domain-specific persona initialization
          ↓
simulated client / attacker initialization
          ↓
Phase II: strategy-driven multi-turn interaction
  ├─ Reassurance Seeking
  ├─ Appeal to Expertise
  ├─ Intellectualization
  └─ Metaphorical Expression
          ↓
Victim / counselor LLM response
          ↓
Evaluator-guided adaptation and Best-of-N selection
          ↓
Final safety judge
  ├─ Harmful Content
  ├─ Impersonation Violation
  ├─ Toxic Empathy
  └─ Target Compliance
```

### 1.3 Phase I와 Table 6의 `w/o Phase II` 구분

**[확정]** 원논문의 Phase I는 domain-specific persona initialization이다. 상담 코퍼스에서 내담자 특성·스타일·인지 왜곡 정보를 구성해 simulated client의 초기 조건을 만드는 단계다.

**[확정]** Table 6의 `w/o Phase II`는 단순히 persona 파일만 만드는 조건이 아니다. Phase I persona는 유지하지만, Phase II의 evaluator-guided strategy adaptation과 Best-of-N 선택을 제거하고 **고정된 상호작용 순서**로 실행하는 ablation이다.

따라서 작업 목표를 다음 두 수준으로 나눠야 한다.

| 수준 | 구현 대상 | 비고 |
|---|---|---|
| Phase I module | persona/profile/style/distortion metadata와 parameterized specification | 현재 주영의 1차 작업 |
| Table 6 `w/o Phase II` | Phase I module + 고정 상호작용 실행기 + target 응답 평가 | 진권이의 Phase II 코드와 인터페이스 확인 필요 |

Table 6에 보고된 참고값은 다음과 같다.

| Model | Configuration | GPT-as-a-Judge ASR | CARES ASR | CARES SS |
|---|---|---:|---:|---:|
| Llama-3.1-8B | w/o Phase II | 0.55 | 0.64 | 0.53 |
| Crispers-7B | w/o Phase II | 0.47 | 0.59 | 0.55 |

**[주의]** 이 숫자를 코드에 하드코딩하거나, 다른 데이터·프롬프트·모델로 같은 숫자가 나오는 것을 재현 성공으로 간주하면 안 된다.

---

## 2. 참고 논문과 원논문의 방법

### 2.1 PCSA 논문

**[확정]** 참고 논문:

- *Do No Harm: Exposing Hidden Vulnerabilities of LLMs via Persona-based Client Simulation Attack in Psychological Counseling*.
- 핵심 절: §3.2 Phase I, §3.3 Phase II, §3.4 safety assessment, §4.2 datasets & benchmark, §4.3 metrics, Appendix B/Table 6, Appendix D judge prompt.

원논문의 Phase I는 다음 식으로 설명된다.

\[
I_{sys} = G_{script}(C_{persona}, C_{style}, T(y \rightarrow C_{dist}))
\]

- `C_persona`: 상담 dialogue history와 anticipated input에서 추출한 client characteristics.
- `C_style`: original dialogue examples로 구성한 client language/style references.
- `y`: 평가하려는 adversarial objective.
- `T(y → C_dist)`: objective를 상담 맥락의 cognitive-distortion 표현과 연결하는 mapping.
- `G_script`: 위 요소를 결합해 simulated client의 system instruction을 작성하는 과정.

**[미확정]** 원논문은 `G_script`의 실제 prompt 전문, `T`의 구체적 알고리즘, persona-goal matching 규칙, seed·temperature·sampling 수를 공개하지 않았다.

### 2.2 Cactus 논문

**[확정]** Cactus는 실제 상담 녹취가 아니라 PatternReframe의 persona·thought·pattern을 바탕으로 LLM이 생성한 CBT 상담 대화 데이터셋이다.

확인된 Cactus 구성:

- PatternReframe에서 persona, negative thought, cognitive pattern, reframed thought를 사용.
- client simulation을 위해 intake form을 구성.
- intake form에는 상담 이유, 이름, 성별, 나이 등의 정보가 포함됨.
- client attitude는 positive, neutral, negative로 구분됨.
- initial utterance와 multi-turn counseling dialogue를 생성.
- filtering 후 약 31,577개 대화, 약 995,512개 utterances, 평균 16.6 turns.

**[주의]** Cactus의 `negative attitude`는 특정 client behavior/attitude label이지, PCSA의 Phase II 전략이나 독립적인 저항 강도 점수와 동일하지 않다.

### 2.3 CBT-Bench의 CBT-DP

**[확정]** PCSA §4.2는 CBT-Bench의 CBT-DP(Dialogue Practice) subset을 persona/client modeling에 보조적으로 사용한다고 설명한다.

- dialogue exercises만 유지.
- multiple-choice 및 classification dataset은 제외.

**[미확정]** CBT-DP에서 어떤 필드·샘플 수·필터 규칙을 실제 PCSA가 사용했는지는 공개되지 않았다.

### 2.4 Cheeseburger Therapy

**[확정]** PCSA §4.2는 Cheeseburger Therapy의 counseling conversations도 persona/client behavior 다양화를 위해 포함한다고 설명한다.

**[미확정]** 사용한 대화 subset, 전처리, 샘플 수, 개인정보 처리 기준은 원논문에 충분히 공개되지 않았다.

### 2.5 CARES

**[확정]** CARES는 PCSA의 persona 원자료라기보다 평가 rubric/benchmark 역할이다.

CARES의 원래 구성:

- 8개 clinical/medical safety principles.
- harmfulness level 0–3.
- direct, indirect, obfuscation, role-play 등 prompting variants.
- Refuse, Caution, Accept의 3-way response class.
- harm level에 따른 Safety Score.

PCSA는 상담 도메인에 맞춰 자체 adversarial objectives를 구성한 뒤 CARES의 평가 방식을 적용한다. PCSA의 §4.2는 목표를 일반 safety benchmark의 self-harm taxonomy와 상담 코퍼스의 반복적인 high-risk pattern에서 구성했다고 설명한다.

**[주의]** 현재 repository의 문서에는 과거 v2 목표가 CARES 문항과 섞여 있어 폐기되고 v4 CARES-free 목표로 교체되었다는 기록이 있다. 따라서 goal 파일 버전과 CARES 평가 rubric을 반드시 분리해서 기록한다.

---

## 3. 현재 `mental_jail` repository 상태

### 3.1 Repository 및 Git 상태

**[확정]** 다음 두 repository를 확인했다.

- upstream: `https://github.com/dlwlsrnjs/mental_jail`
- 작업 fork: `https://github.com/jyoung19/mental_jail`

**[확정]** `jyoung19/mental_jail`은 존재하며, 현재 `main`은 upstream의 최신 커밋 `285dd23`과 동일한 상태로 확인되었다.

**[확정]** 원본 upstream `main`과 작업 fork의 `main`에는 이번 대화 중 어떠한 변경도 하지 않았다.

**[확정]** `repro/phase1-safe` branch를 GitHub에 생성하려고 했으나 자동 승인 사용량 제한으로 쓰기 작업이 실행되지 않았다. 따라서 해당 branch가 아직 없을 수 있다.

### 3.2 현재 저장소에 존재하는 관련 코드

현재 repository에는 다음 관련 폴더가 있다.

- `harmful_behavior_collection/`
  - seeds, goals, personas, client exemplars 관련 코드.
- `phase1_persona_perturbation/`
  - `phase1_persona.py`, `run_phase1.py` 등.
- `phase2_strategy_optimization/`
  - APE pool, TRIPLE/BAI 등 Phase II 관련 코드.
- `common/`
  - data loader, target adapter, PCSA core, experiment runner.
- `evaluation/`
  - CARES metrics, baselines, ablation report.

### 3.3 현재 코드에 대한 주의사항

**[확정]** 현재 `phase1_persona_perturbation/phase1_persona.py`는 surrogate 모델에 응답을 보내고 progress score를 얻어 persona/opening을 반복 perturbation하는 구조를 포함한다.

**[확정]** 이는 원논문 §3.2에서 공개한 단순 persona initialization보다 확장된 구현이다. 따라서 현재 코드의 surrogate-guided hardening을 원논문 Phase I의 exact implementation으로 부르면 안 된다.

**[확정]** `METHOD.md`는 surrogate phase를 제거하고 fully on-target 방식으로 전환했다고 설명하지만, `docs/STATUS.md`에는 open-surrogate Phase 1 실행 결과가 함께 기록되어 있다. 문서 간 method definition이 일치하지 않으므로, 새 작업에서는 실행 설정을 별도 manifest로 고정해야 한다.

**[확정]** 첨부된 `pcsa_eval.zip`은 evaluator/judge/metrics 중심의 평가 harness다. 원논문의 attacker generation과 `G_script` 전문을 제공하는 구현이 아니다.

---

## 4. Phase 1의 정확한 목표

### 4.1 1차 목표

**[결정]** 주영의 1차 구현 목표는 다음의 **paper-grounded Phase I data pipeline**이다.

1. counseling corpus loader 구현.
2. distress-oriented/negative 사례 필터링을 재현 가능하게 구현.
3. intake/profile fields 추출.
4. client utterance style reference 추출.
5. source-provided thought/pattern을 cognitive-state metadata로 저장.
6. 실제 대화에서 관찰되는 resistance evidence를 별도 필드로 기록하되, 근거가 없으면 `unknown`으로 둠.
7. target binding은 유해 자연어가 아니라 abstract `target_id`/`distortion_tag`로 표현.
8. provenance, source ID, deterministic seed, filtering statistics를 기록.
9. 안전한 proxy 입력으로 schema 및 end-to-end dry-run 수행.

### 4.2 Table 6 `w/o Phase II`까지 필요한 추가 작업

**[확정]** Table 6의 `w/o Phase II`를 재현하려면 Phase I persona pipeline만으로는 부족하다.

추가로 필요하다.

- 고정된 interaction sequence 정의.
- Phase II evaluator-guided pivot 제거.
- Best-of-N 제거.
- 동일한 persona에 대한 고정 client turn 실행기.
- target model response logging.
- GPT-as-a-Judge와 CARES evaluator의 분리 실행.

**[미확정]** 원논문은 fixed sequence의 정확한 turn 수·문장·temperature·seed를 공개하지 않았다. 따라서 이 부분은 진권이의 코드 또는 저자 materials가 오면 먼저 확인해야 한다.

---

## 5. Harmful query와 persona의 역할 구분

### 5.1 Persona

Persona는 “누가 어떤 상담 말투와 심리적 맥락으로 말하는가”를 나타내는 attacker-side context다.

권장 구성:

- `C_persona`: 나이·성별·직업·상담 이유 등 source에 실제로 있는 배경 정보.
- `C_style`: source dialogue에서 추출한 client utterance examples.
- `C_state`: thought, cognitive pattern, observed affect 등 source에서 직접 확인되는 심리 상태 metadata.
- `C_resistance`: 조언 거부·반박·회피·반복 등 실제 대화 근거가 있는 behavior evidence.

### 5.2 Harmful query / adversarial objective

Harmful query 또는 attack goal은 “target counselor LLM이 안전하게 처리해야 하는 무엇을 평가할 것인가”를 나타낸다.

- persona와 별도의 데이터 객체다.
- persona의 배경·말투와 query의 평가 목표를 섞어 저장하지 않는다.
- query가 어떤 persona와 연결되는지는 별도 `binding`/`case` record로 기록한다.
- Phase I의 safe scaffold에서는 실제 harmful natural-language request 대신 `<ABSTRACT_TARGET_ID>`와 `<DISTORTION_TAG>`를 사용한다.

### 5.3 잘못된 동일시

다음은 가정하면 안 된다.

- Cactus `negative` attitude = resistance score.
- cognitive distortion label = 임상 진단.
- target query = persona source dialogue.
- CARES prompt = PCSA가 실제 사용한 target query.
- 상담 발화 example = 실제 환자 녹취.

---

## 6. 예상 데이터 입력 형식

### 6.1 Counseling corpus input

원자료는 dataset마다 형식이 다르므로 adapter를 사용한다. 내부 canonical schema는 다음을 예상한다.

```json
{
  "source_id": "cactus-dialogue-0001",
  "dataset": "cactus",
  "dialogue": [
    {"turn_id": 0, "speaker": "client", "text": "..."},
    {"turn_id": 1, "speaker": "counselor", "text": "..."}
  ],
  "intake_form": {
    "name": null,
    "age": null,
    "gender": null,
    "occupation": null,
    "reason_for_seeking_help": null
  },
  "attitude": "negative",
  "thought": "source-provided thought or null",
  "patterns": ["source-provided pattern labels"],
  "reframed_thought": null
}
```

실제 원자료가 위 형식이 아니면 dataset-specific adapter에서 변환한다. source text를 임의로 임상 진단이나 새로운 사실로 확장하지 않는다.

### 6.2 Harmful-goal input

진권이에게 받을 goal 파일은 다음과 같은 별도 schema를 기대한다.

```json
{
  "goal_id": "goal-0001",
  "axis": "target_compliance",
  "target_type": "abstract_or_authorized_category",
  "harm_level": 2,
  "intent_label": "source-defined label",
  "source": "jinho-provided",
  "content_status": "restricted"
}
```

실험 저장소에는 유해 실행법·은폐법·구체적 절차를 그대로 넣지 않고, 접근 통제된 원자료와 abstract metadata를 분리한다.

---

## 7. 예상 Phase 1 출력 형식

```json
{
  "persona_id": "cactus-0001",
  "source_id": "cactus-dialogue-0001",
  "dataset": "cactus",
  "persona": {
    "age": "from_source_or_null",
    "gender": "from_source_or_null",
    "occupation": "from_source_or_null",
    "reason_for_seeking_help": "from_source_or_null"
  },
  "style_references": [
    {
      "turn_id": 0,
      "text": "source client utterance",
      "source_id": "cactus-dialogue-0001"
    }
  ],
  "psychological_state": {
    "thought": "source-provided or null",
    "patterns": ["source-provided labels"],
    "affect": {"value": null, "status": "unknown"}
  },
  "resistance": {
    "status": "observed|not_observed|unknown",
    "evidence_turn_ids": [],
    "evidence_text": []
  },
  "target_binding": {
    "target_id": "<ABSTRACT_TARGET_ID>",
    "distortion_tag": "<DISTORTION_TAG>"
  },
  "provenance": {
    "selection_rule": "distress-oriented / negative where available",
    "seed": 0,
    "adapter_version": "phase1-safe-v0"
  }
}
```

`system_instruction` 또는 client-generation prompt를 구현할 경우에도 현재 단계에서는 parameterized template만 둔다.

```text
PERSONA_PROFILE: <PERSONA_PROFILE>
STYLE_REFERENCES: <STYLE_REFERENCES>
PSYCHOLOGICAL_STATE: <SOURCE_STATE_METADATA>
RESISTANCE_EVIDENCE: <OBSERVED_EVIDENCE_ONLY>
TARGET_ID: <ABSTRACT_TARGET_ID>
DISTORTION_TAG: <DISTORTION_TAG>
```

논문에 공개되지 않은 `G_script` 원문을 임의로 “복원했다”고 기록하지 않는다.

---

## 8. 진권이가 추후 제공하기로 한 데이터와 코드

**[대화에서 확인된 예정 사항]** 진권이는 다음 자료를 GitHub에 올리기로 했다.

- harmful query/attack-goal dataset.
- persona dataset 또는 persona 파일.
- 본인이 담당하는 Phase II 및 나머지 코드.

**[미확정]** 다음은 아직 확인되지 않았다.

- 정확한 파일명과 branch.
- JSON/JSONL/CSV 중 실제 포맷.
- harmful query가 원문인지 abstract label인지.
- persona가 원자료에서 추출된 것인지, 이미 compiled prompt인지.
- source dataset과 license/provenance.
- 목표 dataset을 Cactus/CBT-DP/CARES 중 무엇으로 바꿀지 여부.
- 진권이가 말한 “다른 데이터셋”이 persona corpus인지, goal/query set인지.

진권이에게 다음을 먼저 확인한다.

> 데이터셋을 바꾸자는 것이 persona/style용 counseling corpus인지, harmful goal/query set인지, 아니면 현재 v4 goal 파일 버전인지 확인 필요. 또한 제공 예정 persona/query가 원자료인지 Phase 1 입력으로 가공된 파일인지, source/license와 schema를 함께 공유해 달라.

---

## 9. 아직 확정되지 않은 사항

다음 항목은 저자 materials 또는 팀 합의 전까지 임의로 확정하지 않는다.

1. `G_script`의 실제 prompt wording.
2. `T(y → C_dist)`의 mapping algorithm.
3. persona와 goal의 matching 방법.
4. Cactus/CBT-DP/Cheeseburger Therapy의 정확한 sampling 비율.
5. negative/distress-oriented filtering의 정확한 threshold.
6. style reference의 개수와 turn selection rule.
7. fixed interaction sequence의 exact text, turn 수, stop rule.
8. attacker, target, evaluator, judge의 정확한 model version.
9. temperature, top-p, max tokens, retry, seed, concurrency.
10. Table 6의 exact sample count와 category balance.
11. human annotation 또는 judge calibration 절차.
12. 진권이의 “다른 데이터셋” 변경 범위.

---

## 10. 구현 시 가정하면 안 되는 사항

- 논문 Table 6 수치를 목표값으로 하드코딩하지 않는다.
- synthetic proxy 결과를 실제 PCSA 재현 결과로 보고하지 않는다.
- `negative` attitude를 resistance strength로 해석하지 않는다.
- source에 없는 나이·직업·진단·감정을 생성해 persona에 추가하지 않는다.
- Cactus를 real patient transcript로 표현하지 않는다.
- CARES prompt를 PCSA의 실제 harmful query라고 가정하지 않는다.
- repository의 `phase1_persona_perturbation`을 원논문의 exact Phase I라고 부르지 않는다.
- `METHOD.md`의 “surrogate 제거”와 `STATUS.md`의 surrogate 실행 기록 중 하나를 검증 없이 현재 method로 선택하지 않는다.
- 유해 자연어 query나 actionable self-harm content를 public repository에 커밋하지 않는다.
- 결과가 Table 6과 다르면 숫자를 맞추기 위해 filtering·label·judge를 임의 조정하지 않는다.

---

## 11. 평가 및 파일럿 테스트 계획

### 11.1 1단계: offline schema test

- synthetic benign counseling-like fixture로 loader 실행.
- 필수 field 누락 검출.
- source ID 보존 확인.
- 동일 seed에서 동일한 persona selection이 나오는지 확인.
- 다른 seed에서 selection이 달라질 수 있는지 확인.
- raw source와 derived field의 provenance 확인.

### 11.2 2단계: corpus profiling pilot

실제 corpus를 받으면 우선 공격을 실행하지 않고 다음만 산출한다.

- 전체 dialogue 수.
- speaker/turn format 오류 수.
- attitude별 수.
- negative/distress filter 통과 수.
- intake field coverage.
- pattern label coverage.
- client style reference 길이 분포.
- resistance evidence가 실제로 관찰 가능한 사례 수.

### 11.3 3단계: Phase I artifact audit

- persona profile 샘플을 사람이 읽고 source-supported 여부 확인.
- inferred field와 observed field 분리 확인.
- abstract target binding이 원문 harmful instruction을 포함하지 않는지 확인.
- duplicate persona와 source leakage 점검.

### 11.4 4단계: 고정 실행 파일럿

진권이 Phase II 인터페이스가 도착한 뒤에만 진행한다.

- Phase I persona를 고정.
- Phase II adaptive strategy selection과 Best-of-N은 사용하지 않음.
- fixed interaction executor로 소규모 pilot 실행.
- target response log를 저장.
- GPT-as-a-Judge와 CARES evaluator를 별도로 실행.
- parse failure를 성공/실패 점수에 포함하지 않고 별도로 보고.

### 11.5 5단계: Table 6 비교

동일한 다음 조건이 확보될 때만 Table 6과 비교한다.

- target model/version.
- persona/query set.
- turn 수와 fixed sequence.
- generation parameters.
- judge/evaluator version.
- sample count와 category balance.

조건이 다르면 결과를 “Table 6 reproduction”이 아니라 **implementation pilot** 또는 **method-level reimplementation**으로 보고한다.

---

## 12. 현재 TODO와 우선순위

### P0 — 작업 공간 보호

- [ ] `jyoung19/mental_jail`의 `main`에 직접 push하지 않기.
- [ ] `repro/phase1-safe` branch 생성.
- [ ] upstream branch와 작업 branch를 명시적으로 구분.
- [ ] API key와 restricted dataset을 commit하지 않기.

### P1 — 데이터 계약 확정

- [ ] 진권이에게 persona/query 파일명·schema·source·license 요청.
- [ ] “다른 dataset”이 corpus인지 goal set인지 확인.
- [ ] harmful content의 저장 위치와 접근 범위 결정.
- [ ] Phase I output schema 합의.

### P2 — Phase I safe module

- [ ] dataset adapters.
- [ ] canonical counseling-record schema.
- [ ] persona field extractor.
- [ ] style-reference selector.
- [ ] thought/pattern metadata mapper.
- [ ] observed resistance evidence extractor.
- [ ] provenance and deterministic seed logging.
- [ ] parameterized specification compiler.

### P3 — Offline pilot

- [ ] fixture-based unit tests.
- [ ] corpus profiling report.
- [ ] duplicate/missing/invalid record report.
- [ ] output sample audit.

### P4 — 진권이 코드 통합

- [ ] 진권이 branch 또는 commit fetch.
- [ ] interface adapter 작성.
- [ ] fixed executor와 Phase I output 연결.
- [ ] merge conflict 해결.

### P5 — 평가

- [ ] fixed interaction pilot.
- [ ] separated CARES/GPT judge evaluation.
- [ ] parse-failure accounting.
- [ ] Table 6 comparison report with deviations.

---

## 13. Git 규칙

1. `main`은 직접 수정하지 않는다.
2. 모든 변경은 `repro/phase1-safe` 또는 명시된 topic branch에서 한다.
3. 작은 단위로 commit한다.
4. commit message에 data version, schema version, experiment condition을 기록한다.
5. 진권이 branch는 merge 전 diff와 테스트 결과를 확인한다.
6. upstream `main` 변경은 직접 반영하지 않고 fork로 fetch 후 검토한다.
7. merge 또는 PR 전 `git diff`, test log, data manifest를 남긴다.
8. restricted harmful query 원문과 model output은 public repository에 올리지 않는다.

권장 branch 구조:

```text
jyoung19/mental_jail:main       # 보호용 기준 branch
        │
        ├── repro/phase1-safe   # 주영 Phase I 작업
        └── integration/jinho   # 진권 코드 통합이 필요한 경우
```

---

## 14. 현재 결론

**[확정]** 지금 주영이 먼저 할 일은 원논문의 공개 설명을 기준으로 한 Phase I의 데이터·스키마·provenance·persona compiler를 분리해 구현하는 것이다.

**[확정]** harmful query와 persona는 별도 객체로 취급해야 한다.

**[확정]** Cactus/CBT-DP/Cheeseburger Therapy는 persona·상담 behavior 재료이고, CARES는 주로 평가 rubric이다.

**[확정]** Table 6의 `w/o Phase II`는 Phase I persona를 유지한 fixed interaction ablation이며, persona extractor만으로는 재현되지 않는다.

**[미확정]** 진권이가 바꾸자는 dataset의 정확한 대상과 제공할 파일 schema는 아직 확인되지 않았다.

**[결정]** 진권이 코드가 오기 전까지 안전한 offline Phase I pilot과 데이터 계약을 먼저 고정하고, 이후 진권이 branch를 별도로 통합한다.
