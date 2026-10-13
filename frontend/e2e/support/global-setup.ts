import { resetRateLimits } from './backend'

export default function globalSetup() {
  resetRateLimits()
}
