from .models import User

def create_google_user(strategy, details, backend, user=None, *args, **kwargs):
    if user:
        return {"user": user}

    email = details.get("email")
    full_name = details.get("fullname") or details.get("first_name", "")

    existing_user = User.objects.filter(email=email).first()
    if existing_user:
        if not existing_user.is_active:
            existing_user.is_active = True
            existing_user.save()
        return {"user": existing_user}

    user = User.objects.create(
        email=email,
        full_name=full_name,
        signup_method=User.SignupMethod.EMAIL,
        is_active=True,
    )

    return {"user": user}
