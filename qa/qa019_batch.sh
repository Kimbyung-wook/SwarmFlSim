#!/usr/bin/env bash
# QA-019: 같은 시드 lockstep 반복 실행 (--trace-io). 사용: qa/qa019_batch.sh <base_port> <frames> <n> <variant>...
# variant: base | nosensor | nopayload | noloss | range. 환경 변수 PREFIX(기본 q19)로 출력 이름을 바꾼다 (TC-QA-040: PREFIX=a40)
# 환경 변수 AGENT_ARGS가 있으면 Agent 인자로 넘긴다 (TC-QA-048: AGENT_ARGS='--activity-max-hz 2')
set -u
cd "$(dirname "$0")/.."
port=$1; frames=$2; n=$3; shift 3
for v in "$@"; do
  if [ "$v" = base ]; then sc=scenario/examples/p5_payload_demo_5.json; else sc=qa/scenarios/qa_p5_$v.json; fi
  for i in $(seq 1 "$n"); do
    out=qa/out/p5/${PREFIX:-q19}_${v}_$i
    rm -rf "$out"
    echo "$(date +%T) start $v #$i port $port"
    uv run --with psutil python -X utf8 qa/p5_e2e.py --mode lockstep --scenario "$sc" --frames "$frames" --trace-io \
      --base-port "$port" --out "$out" ${AGENT_ARGS:+--agent-arg "$AGENT_ARGS"} > "qa/out_${PREFIX:-q19}_${v}_$i.log" 2>&1
    echo "$(date +%T) end $v #$i rc $?"
  done
done
echo ALLDONE
