export class PollingRegistry {
  private timerByKey = new Map<string, ReturnType<typeof setInterval>>()

  set(key: string, timer: ReturnType<typeof setInterval>) {
    this.clear(key)
    this.timerByKey.set(key, timer)
  }

  get(key: string): ReturnType<typeof setInterval> | undefined {
    return this.timerByKey.get(key)
  }

  clear(key: string) {
    const timer = this.timerByKey.get(key)
    if (timer) {
      clearInterval(timer)
      this.timerByKey.delete(key)
    }
  }

  clearAll() {
    this.timerByKey.forEach((timer) => {
      clearInterval(timer)
    })
    this.timerByKey.clear()
  }
}
