export default function ConfidenceDot({ lowConfidence, verified }: { lowConfidence: boolean; verified: boolean }) {
  if (verified) {
    return <span title="Reviewed by you" className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />
  }
  if (lowConfidence) {
    return <span title="Low-confidence extraction — please check this row" className="inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />
  }
  return <span title="Extracted with high confidence" className="inline-block h-2.5 w-2.5 rounded-full bg-slate-300" />
}
