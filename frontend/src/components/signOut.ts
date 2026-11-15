/** A plain form post: /logout clears the session and redirects to the sign-in page. */
export function signOut() {
  const form = document.createElement('form')
  form.method = 'post'
  form.action = '/logout'
  document.body.append(form)
  form.submit()
}
