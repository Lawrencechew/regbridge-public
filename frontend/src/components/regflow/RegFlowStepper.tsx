import type { WorkflowStep } from '../../types/regflow'

const steps = [
  { key: 'select', label: 'Select' },
  { key: 'upload', label: 'Upload' },
  { key: 'map', label: 'Map' },
  { key: 'preflight', label: 'Preflight' },
  { key: 'generate', label: 'Generate' },
] as const

function activeIndex(step: WorkflowStep): number {
  if (step === 'inspect') return 1
  if (step === 'complete') return 4
  return steps.findIndex((item) => item.key === step)
}

export function RegFlowStepper({ step }: { step: WorkflowStep }) {
  const current = activeIndex(step)
  return (
    <nav className="stepper" aria-label="RegFlow progress">
      <ol>
        {steps.map((item, index) => (
          <li
            key={item.key}
            className={index === current ? 'active' : index < current ? 'complete' : ''}
            aria-current={index === current ? 'step' : undefined}
          >
            <span>{index < current ? '✓' : index + 1}</span>
            <strong>{item.label}</strong>
          </li>
        ))}
      </ol>
    </nav>
  )
}
