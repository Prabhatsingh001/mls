from authentication.utils import _generate_file_name

def service_item_image_path(instance, filename):
    image_name, ext = _generate_file_name(instance, filename)
    return f"service_items/{image_name}_item{ext}"

def work_proof_image_path(instance, filename):
    image_name, ext = _generate_file_name(instance, filename)
    return f"work_proofs/{image_name}_proof{ext}"