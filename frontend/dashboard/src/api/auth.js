import api from './client'

export default {
  csrf: () => api.get('/auth/csrf/'),
  me: () => api.get('/auth/me/'),
  login: (username, password) => api.post('/auth/login/', { username, password }),
  register: (payload) => api.post('/auth/register/', payload),
  logout: () => api.post('/auth/logout/'),
  requestAccess: (payload) => api.post('/auth/request-access/', payload),
}
