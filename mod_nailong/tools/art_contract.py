"""Single readiness contract for hair-preserving, collar-reviewed portrait art."""
def portrait_ready(row):
    collar=row.get('collar_fit',{})
    return (row.get('review')=='approved' and row.get('art_direction')=='hair-features-v1'
            and collar.get('status')=='approved' and collar.get('policy')=='collar-fit-v1'
            and collar.get('image_sha256')==row.get('image_sha256'))
