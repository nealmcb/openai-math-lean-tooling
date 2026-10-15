#!/bin/bash
# cloud_long_nanoda: the nanoda-only pipeline (export, then nanoda, no Lean kernel replay) for the long-check configurations, on a big cloud machine.
#
# Purpose: the 18 configurations whose laptop check took over 2000 s (listed in LONG below) are the ones where Lean's own replay is the slow part. The
# fast alternative is: the build already exists, so export the solution with lean4export (single-threaded; the floor on wall time) and let nanoda check
# the export with many threads and a 1 GiB checker stack. This runs tools/nanoda_scaling.py once per configuration at THREADS threads, JOBS configurations
# at a time, longest laptop check first; results (export seconds and size in results/nanoda-scaling.jsonl, wall/CPU/RSS per run, per-declaration times in
# scratch/nanoda-scaling/CONFIG.N.times) are uploaded to s3://BUCKET/long-nanoda/ every 15 minutes and at the end; at the end the machine is powered off
# (an instance with shutdown behaviour "stop" stops). A cost guard powers it off after GUARD_H hours regardless.
# Needs the repository on the volume, the closure built, ext/bin/nanoda_bin.timing, and an instance role that can write the bucket.
# Usage: cloud_long_nanoda.sh [BUCKET] [JOBS=10] [THREADS=8] [GUARD_H=7]
BUCKET=${1:-experiment-618-openai-math-a2ea0dcc}; JOBS=${2:-10}; THREADS=${3:-8}; GUARD_H=${4:-7}
cd "$(dirname "$0")/.." || exit 1
LONG="MUBSix UniversalTensorSquares LaughlinFock GeneralMahler TriangularEnergy TriangularGaussian AtomicGaussian CoarseAssembly SKRatio Laughlin LaughlinPlanar LaughlinGap StrongKadisonKastler FactorGeneration ErdosReciprocal DuttaDomain RelativeGeneration OstmannPrimes"
mkdir -p results/long-nanoda
sudo shutdown -h +$((GUARD_H * 60)) "cost guard of cloud_long_nanoda"
date -Is > results/long-nanoda/STARTED
( while true; do sleep 900; aws s3 sync results/long-nanoda s3://$BUCKET/long-nanoda/ --only-show-errors; aws s3 cp results/nanoda-scaling.jsonl s3://$BUCKET/long-nanoda/nanoda-scaling.jsonl --only-show-errors; done ) &
SYNC=$!
printf '%s\n' $LONG | xargs -P "$JOBS" -I{} bash -c 'python3 -I tools/nanoda_scaling.py {} --threads '"$THREADS"' --timeout 14400 > results/long-nanoda/{}.log 2>&1; echo "$(date -Is) {} rc $?" >> results/long-nanoda/done.log'
kill $SYNC
date -Is > results/long-nanoda/FINISHED
aws s3 sync results/long-nanoda s3://$BUCKET/long-nanoda/ --only-show-errors; aws s3 cp results/nanoda-scaling.jsonl s3://$BUCKET/long-nanoda/nanoda-scaling.jsonl --only-show-errors
aws s3 sync scratch/nanoda-scaling s3://$BUCKET/long-nanoda/times/ --exclude '*' --include '*.times' --only-show-errors
sudo shutdown -h +2 "cloud_long_nanoda finished"
