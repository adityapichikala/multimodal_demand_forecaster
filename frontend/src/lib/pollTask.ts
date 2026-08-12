

// frontend/src/lib/pollTask.ts

export interface TaskResult {
  task_id: string
  status: 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE' | 'REVOKED'
  result: unknown | null
  error: string | null
  hint?: string
}

/**
 * Polls /task/{taskId} with exponential backoff until the task succeeds,
 * fails, or the client-side timeout is reached.
 *
 * @param taskId     The Celery task ID returned by /train-async
 * @param timeoutMs  Client-side timeout in ms (default: 90 seconds)
 * @param onProgress Optional callback called on each PENDING/STARTED poll
 *                   with elapsed time — useful for updating a progress bar
 * @returns          The task result on SUCCESS
 * @throws           Error with user-friendly message on FAILURE or timeout
 */
export async function pollTaskWithTimeout(
  taskId: string,
  timeoutMs: number = 90_000,
  onProgress?: (elapsedMs: number, pollCount: number) => void
): Promise<unknown> {
  const start = Date.now()
  let delay = 2_000   // Start polling at 2s
  let pollCount = 0

  while (true) {
    const elapsed = Date.now() - start

    // Client-side timeout check — runs BEFORE the fetch so we don't
    // waste a round-trip when we're already over budget.
    if (elapsed >= timeoutMs) {
      throw new Error(
        'Forecast timed out after 90 seconds. ' +
        'Please try with a smaller date range or fewer products.'
      )
    }

    const res = await fetch(`/task/${taskId}`)

    if (!res.ok) {
      throw new Error(`Server error while checking task status: ${res.status}`)
    }

    const data: TaskResult = await res.json()
    pollCount++

    if (data.status === 'SUCCESS') {
      return data.result
    }

    if (data.status === 'FAILURE' || data.status === 'REVOKED') {
      throw new Error(
        data.error ??
        'Forecasting failed. Please check your data format and try again.'
      )
    }

    // Still PENDING or STARTED — notify caller and wait with backoff
    if (onProgress) {
      onProgress(elapsed, pollCount)
    }

    await sleep(delay)

    // Exponential backoff: 2s → 3s → 4.5s → 6.75s → 10s (capped)
    delay = Math.min(delay * 1.5, 10_000)
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}