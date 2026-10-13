import { Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { AccountPage } from './pages/AccountPage'
import { BookPage } from './pages/BookPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { NewImportPage } from './pages/NewImportPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { RecipePage } from './pages/RecipePage'
import { RegisterPage } from './pages/RegisterPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { VerifyEmailPage } from './pages/VerifyEmailPage'
import { RedirectIfAuthenticated, RequireAuth } from './session/guards'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route
          index
          element={
            <RedirectIfAuthenticated>
              <LandingPage />
            </RedirectIfAuthenticated>
          }
        />
        <Route
          path="cadastro"
          element={
            <RedirectIfAuthenticated>
              <RegisterPage />
            </RedirectIfAuthenticated>
          }
        />
        <Route
          path="entrar"
          element={
            <RedirectIfAuthenticated>
              <LoginPage />
            </RedirectIfAuthenticated>
          }
        />
        <Route path="verificar-email" element={<VerifyEmailPage />} />
        <Route path="esqueci-senha" element={<ForgotPasswordPage />} />
        <Route path="redefinir-senha" element={<ResetPasswordPage />} />
        <Route
          path="livro"
          element={
            <RequireAuth>
              <BookPage />
            </RequireAuth>
          }
        />
        <Route
          path="nova"
          element={
            <RequireAuth>
              <NewImportPage />
            </RequireAuth>
          }
        />
        <Route
          path="receitas/:id"
          element={
            <RequireAuth>
              <RecipePage />
            </RequireAuth>
          }
        />
        <Route
          path="conta"
          element={
            <RequireAuth>
              <AccountPage />
            </RequireAuth>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
